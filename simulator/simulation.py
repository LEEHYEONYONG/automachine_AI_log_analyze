from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from random import Random

from faults import FAULT_TYPES, FaultEngine
from simulator.alarms import ALARMS
from simulator.clock import VirtualClock
from simulator.logger import CsvSink, MachineLogger
from simulator.machine import Machine
from simulator.operator import Operator

SENSOR_FIELDS = [
    "timestamp", "mode", "loader_vac_kpa", "disp_pressure_kpa", "disp_valve_open",
    "disp_temp_c", "syringe_level_pct",
]
HIDDEN_FIELDS = [
    "timestamp", "nozzle_open_ratio", "pick_leak_ratio", "achievable_vac_kpa",
    "temp_true_c", "temp_sensor_offset_c", "material_viscosity", "active_faults",
]


class Simulation:
    """Wires the machine, operator and fault engine together and writes all outputs.

    logs/<run_id>/          what the machine records (input for analysis)
    ground_truth/<run_id>/  what really happened (only for evaluating the analysis)
    """

    def __init__(self, machine_cfg: dict, scenario: dict, out_root: Path, seed: int | None = None):
        self.scenario = scenario
        self.seed = scenario.get("seed", 0) if seed is None else seed
        start = datetime.fromisoformat(scenario["start_time"])
        # The run id must not reveal the scenario, or the analysis could just read the folder name.
        digest = hashlib.sha1(f"{scenario['name']}:{self.seed}".encode()).hexdigest()[:6]
        self.run_id = f"{start:%Y%m%d_%H%M}_{digest}"

        self.clock = VirtualClock(start, machine_cfg["tick_s"])
        self.cfg = machine_cfg
        self.log_dir = out_root / "logs" / self.run_id
        self.truth_dir = out_root / "ground_truth" / self.run_id
        self.truth_dir.mkdir(parents=True, exist_ok=True)

        self.log = MachineLogger(self.log_dir, self.clock, SENSOR_FIELDS)
        # Separate random streams so adding a fault does not reshuffle unrelated randomness.
        self.machine = Machine(machine_cfg, self.clock, self.log, Random(f"{self.seed}-machine"))
        self.operator = Operator(self.machine, Random(f"{self.seed}-operator"))
        self.faults = FaultEngine([
            FAULT_TYPES[spec["type"]](f"F{i + 1:03d}", start + timedelta(minutes=spec["start_after_min"]),
                                      spec.get("params", {}))
            for i, spec in enumerate(scenario.get("faults", []))
        ])
        self.machine.maintenance_listeners.append(lambda action: self.faults.on_maintenance(action, self.clock.now))
        self._hidden = CsvSink(self.truth_dir / "hidden_state.csv", HIDDEN_FIELDS)
        self._sensor_rng = Random(f"{self.seed}-sensor")
        self.latest_sensors: dict = {}
        self._closed = False

    def inject_fault(self, fault_type: str, params: dict | None = None):
        """Start a fault right now (used by the engineer console during a live run)."""
        fault_id = f"F{len(self.faults.faults) + 1:03d}"
        fault = FAULT_TYPES[fault_type](fault_id, self.clock.now, params or {})
        self.faults.faults.append(fault)
        return fault

    def run(self, hours: float | None = None) -> dict:
        hours = self.scenario.get("duration_hours", 8) if hours is None else hours
        self.operator.start_shift()
        for _ in range(round(hours * 3600 / self.clock.dt)):
            self.step()
        self.close()
        return self.summary()

    def step(self) -> None:
        now = self.clock.now
        self.faults.update(self.machine, now)
        self.machine.step()
        self.operator.update(now)
        if self.clock.every(self.cfg["sensor_sample_s"]):
            self._sample_sensors()
        if self.clock.every(self.cfg["hidden_sample_s"]):
            self._sample_hidden()
        self.clock.tick()

    def flush(self) -> None:
        self.log.flush()
        self._hidden.flush()

    def engineer_view(self) -> dict:
        """Hidden state for the engineer console. Never shown on the HMI."""
        p = self.machine.physics
        return {
            "faults": [f.truth() for f in self.faults.faults],
            "hidden": {
                "nozzle_open_ratio": round(p.dispenser.nozzle_open_ratio, 4),
                "pick_leak_ratio": round(p.loader.leak_ratio, 4),
                "achievable_vac_kpa": round(p.loader.achievable_vacuum_kpa, 2),
                "temp_true_c": round(p.dispenser.temp_true_c, 3),
                "temp_sensor_offset_c": round(self.machine.sensors["disp_temp"].offset, 3),
                "material_viscosity": round(p.dispenser.material_viscosity, 4),
            },
        }

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.log.close()
        self._hidden.close()
        self._write_machine_info()
        self._write_ground_truth()

    def summary(self) -> dict:
        total = self.machine.counts.total()
        return {
            "run_id": self.run_id,
            "simulated_until": self.log.timestamp(),
            "parts": total,
            "ok": self.machine.counts["OK"],
            "ng": self.machine.counts["NG"],
            "yield_pct": round(100.0 * self.machine.counts["OK"] / total, 2) if total else 0.0,
            "alarms": dict(sorted(self.machine.alarm_counts.items())),
            "log_dir": str(self.log_dir),
            "ground_truth_dir": str(self.truth_dir),
        }

    def _sample_sensors(self) -> None:
        m = self.machine
        p = m.physics
        rng = self._sensor_rng
        vac_true = p.loader.achievable_vacuum_kpa if m.loader.vacuum_on else 0.0
        pressure_true = (m.dispenser.dispensing_pressure_kpa() if m.dispenser.valve_open
                         else m.recipe["dispense_pressure_kpa"])
        self.latest_sensors = {
            "timestamp": m.log.timestamp(),
            "mode": m.mode.value,
            "loader_vac_kpa": m.sensors["loader_vac"].read(vac_true, rng),
            "disp_pressure_kpa": m.sensors["disp_pressure"].read(pressure_true, rng),
            "disp_valve_open": int(m.dispenser.valve_open),
            "disp_temp_c": m.sensors["disp_temp"].read(p.dispenser.temp_true_c, rng),
            "syringe_level_pct": round(m.dispenser.level_pct, 1),
        }
        m.log.sensor(self.latest_sensors)

    def _sample_hidden(self) -> None:
        p = self.machine.physics
        self._hidden.write({
            "timestamp": self.log.timestamp(),
            "nozzle_open_ratio": round(p.dispenser.nozzle_open_ratio, 4),
            "pick_leak_ratio": round(p.loader.leak_ratio, 4),
            "achievable_vac_kpa": round(p.loader.achievable_vacuum_kpa, 2),
            "temp_true_c": round(p.dispenser.temp_true_c, 3),
            "temp_sensor_offset_c": round(self.machine.sensors["disp_temp"].offset, 3),
            "material_viscosity": round(p.dispenser.material_viscosity, 4),
            "active_faults": ";".join(f.fault_id for f in self.faults.active()),
        })

    def _write_machine_info(self) -> None:
        """Equipment facts an engineer would know anyway: recipe and alarm code list. No fault info."""
        info = {
            "machine_id": self.machine.machine_id,
            "start_time": self.clock.start.isoformat(),
            "end_time": self.clock.now.isoformat(timespec="milliseconds"),
            "recipe": self.cfg["recipe"],
            "alarm_codes": [dataclasses.asdict(a) for a in ALARMS.values()],
        }
        (self.log_dir / "machine_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")

    def _write_ground_truth(self) -> None:
        truth = {
            "run_id": self.run_id,
            "scenario": self.scenario["name"],
            "scenario_description": self.scenario.get("description", ""),
            "seed": self.seed,
            "faults": [f.truth() for f in self.faults.faults],
        }
        (self.truth_dir / "faults.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
