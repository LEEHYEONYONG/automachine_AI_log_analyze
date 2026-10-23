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
    "timestamp", "plant_air_kpa", "regulator_out_kpa", "nozzle_open_ratio", "pick_leak_ratio",
    "achievable_vac_kpa", "temp_true_c", "temp_sensor_offset_c", "material_viscosity", "syringe_age_h",
    "needle_z_offset_mm", "needle_xy_offset_mm", "tip_buildup", "bubbles", "active_faults",
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
        self.operator = Operator(self.machine, Random(f"{self.seed}-operator"), machine_cfg["plant"],
                                 machine_cfg["operator"], scenario.get("schedule"))
        self.faults = FaultEngine([
            FAULT_TYPES[spec["type"]](f"F{i + 1:03d}", start + timedelta(minutes=spec["start_after_min"]),
                                      spec.get("params", {}))
            for i, spec in enumerate(scenario.get("faults", []))
        ])
        self._fault_rng = Random(f"{self.seed}-faults")
        self.machine.maintenance_listeners.append(self._on_maintenance)
        self._hidden = CsvSink(self.truth_dir / "hidden_state.csv", HIDDEN_FIELDS)
        self._sensor_rng = Random(f"{self.seed}-sensor")
        self.latest_sensors: dict = {}
        self._closed = False

    def inject_fault(self, fault_type: str, params: dict | None = None, delay_min: float = 0.0,
                     origin: str = "injected"):
        """Schedule a fault (engineer console, or a natural event / operator mistake)."""
        start = self.clock.now + timedelta(minutes=delay_min)
        fault = FAULT_TYPES[fault_type](self.faults.next_id(), start, params or {}, origin)
        self.faults.add(fault)
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
        self._write_ground_truth()

    def engineer_view(self) -> dict:
        """Hidden state for the engineer console. Never shown on the HMI."""
        now = self.clock.now
        changed = {k: v for k, v in self.machine.setpoints.items() if self.machine.recipe.get(k) != v}
        return {
            "truth_file": str(self.truth_dir / "faults.json"),
            "faults": [
                {**f.truth(), "progress": round(f.progress(((f.resolved_at or now) - f.injected_at).total_seconds()), 3)
                 if f.injected_at else 0.0}
                for f in self.faults.faults
            ],
            "hidden": self._hidden_values(),
            "setpoint_errors": changed,
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
            "faults": [f"{f.fault_id} {f.type} ({f.origin})" for f in self.faults.faults],
            "log_dir": str(self.log_dir),
            "ground_truth_dir": str(self.truth_dir),
        }

    # ---- natural events and operator mistakes ------------------------------------

    def _on_maintenance(self, action: str, by: str) -> None:
        """Resolve faults fixed by this action, then roll for side effects of doing it."""
        self.faults.on_maintenance(action, self.clock.now)
        rng = self._fault_rng
        natural = self.cfg["natural"]
        mistakes = self.cfg["operator"]
        by_simulated_operator = by != "HMI"  # a person at the HMI makes their own mistakes

        if action == "replace_syringe" and rng.random() < natural["air_bubble_on_syringe_change"]:
            self.inject_fault("air_bubble", {"bubbles": rng.randint(5, 20),
                                             "void_probability": round(rng.uniform(0.08, 0.2), 3)},
                              origin="natural: air trapped while changing the syringe")
        if (action == "nozzle_clean" and by_simulated_operator
                and rng.random() < mistakes["skip_calibration_probability"]):
            self.inject_fault("needle_offset", {"dz_mm": round(rng.uniform(0.03, 0.08), 3),
                                                "dxy_mm": round(rng.uniform(0.0, 0.05), 3)},
                              origin=f"operator_error: {by} re-mounted the needle without calibration")
        if action == "model_change":
            if rng.random() < natural["setup_offset_on_model_change"]:
                self.inject_fault("needle_offset", {"dz_mm": 0.0, "dxy_mm": round(rng.uniform(0.06, 0.14), 3)},
                                  origin="natural: dispense position not re-taught after model change")
            if by_simulated_operator and rng.random() < mistakes["recipe_typo_probability"]:
                if rng.random() < 0.5:
                    wrong = round(self.machine.setpoints["dispense_pressure_kpa"] * 0.82)
                    self.inject_fault("recipe_pressure_error", {"wrong_pressure_kpa": float(wrong)},
                                      origin=f"operator_error: {by} mistyped the pressure during model change")
                else:
                    self.inject_fault("recipe_retract_error", {"wrong_retract_delay_s": 0.0},
                                      origin=f"operator_error: {by} cleared the retract delay during model change")

    # ---- outputs ----------------------------------------------------------------

    def _sample_sensors(self) -> None:
        m = self.machine
        p = m.physics
        rng = self._sensor_rng
        vac_true = p.loader.achievable_vacuum_kpa if m.loader.vacuum_on else 0.0
        pressure_true = (m.dispenser.dispensing_pressure_kpa() if m.dispenser.valve_open
                         else p.dispenser.regulator_out_kpa)
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

    def _hidden_values(self) -> dict:
        p = self.machine.physics
        d = p.dispenser
        return {
            "plant_air_kpa": round(p.air.supply_kpa, 1),
            "regulator_out_kpa": round(d.regulator_out_kpa, 1),
            "nozzle_open_ratio": round(d.nozzle_open_ratio, 4),
            "pick_leak_ratio": round(p.loader.leak_ratio, 4),
            "achievable_vac_kpa": round(p.loader.achievable_vacuum_kpa, 2),
            "temp_true_c": round(d.temp_true_c, 3),
            "temp_sensor_offset_c": round(self.machine.sensors["disp_temp"].offset, 3),
            "material_viscosity": round(d.material_viscosity, 4),
            "syringe_age_h": round(d.syringe_age_h, 3),
            "needle_z_offset_mm": round(d.needle_z_offset_mm, 3),
            "needle_xy_offset_mm": round(d.needle_xy_offset_mm, 3),
            "tip_buildup": round(d.tip_buildup, 3),
            "bubbles": d.bubbles,
        }

    def _sample_hidden(self) -> None:
        self._hidden.write({
            "timestamp": self.log.timestamp(),
            **self._hidden_values(),
            "active_faults": ";".join(f.fault_id for f in self.faults.active()),
        })

    def _write_machine_info(self) -> None:
        """Equipment facts an engineer would know anyway: recipes, alarm codes, breaks. No fault info."""
        info = {
            "machine_id": self.machine.machine_id,
            "start_time": self.clock.start.isoformat(),
            "end_time": self.clock.now.isoformat(timespec="milliseconds"),
            "recipes": self.cfg["recipes"],
            "planned_breaks": self.cfg["plant"]["breaks"],
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
