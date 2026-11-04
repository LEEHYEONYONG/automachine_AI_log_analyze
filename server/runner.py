from __future__ import annotations

import asyncio
import copy
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

from simulator import settings as machine_settings
from simulator.simulation import Simulation

FRAME_S = 0.1          # how often state is pushed to the browser
FLUSH_S = 1.0          # how often log files are flushed to disk
MAX_SPEED = 1000.0
STALL_S = 30.0         # no frame for this long means the machine has stopped moving


class SimRunner:
    """Advances a Simulation in step with wall-clock time, scaled by `speed`."""

    def __init__(self, root: Path, out_root: Path | None = None, seed: int | None = None):
        self.root = root
        self.out_root = out_root or root
        self.seed = seed  # fixed seed for reproducible live runs (tests); None = new seed per run
        # The shipped file is the standard; settings changed on the HMI are kept in state/ and laid over it,
        # so they survive a restart. Batch runs for evaluation never read state/.
        self.standard_cfg = json.loads((root / "config" / "machine.json").read_text(encoding="utf-8"))
        self.machine_cfg = copy.deepcopy(self.standard_cfg)
        self.settings_file = self.out_root / "state" / "machine_settings.json"
        self.saved = self._load_saved()
        for key, value in self.saved.get("machine", {}).items():
            if key in machine_settings.SPEC:
                machine_settings.put(self.machine_cfg, key, machine_settings.coerce(key, value))
        self.sim: Simulation | None = None
        self.scenario_name = "live"
        self.speed = 1.0
        self.paused = False
        self._debt = 0.0
        self.session = None  # HmiSession, set by the app
        self.last_frame: float | None = None  # when the real-time loop last ran; None without a loop

    def _load_saved(self) -> dict:
        """Settings saved from the HMI. A missing or broken file means the shipped values."""
        try:
            return json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_settings(self, session_values: dict | None = None) -> None:
        """Write the settings that differ from the shipped file (with the session's), so a restart keeps them."""
        changed = {k: v for k, v in machine_settings.current(self.machine_cfg).items()
                   if v != machine_settings.get(self.standard_cfg, k)}
        self.saved = {"machine": changed, "session": session_values or self.saved.get("session", {})}
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.settings_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.saved, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.settings_file)

    def loop_stalled(self) -> bool:
        """The HTTP API keeps answering when the loop dies, so only this shows the machine has stopped moving.
        A paused simulation still runs frames."""
        return self.last_frame is not None and time.perf_counter() - self.last_frame > STALL_S

    def scenarios(self) -> list[str]:
        return sorted(p.stem for p in (self.root / "config" / "scenarios").glob("*.json"))

    def new_run(self, scenario_name: str | None = None) -> None:
        """Close the current run and start a fresh one. The machine starts STOPPED."""
        auto = self.sim.operator.enabled if self.sim else True
        if self.sim:
            self.sim.close()
        if scenario_name:
            path = self.root / "config" / "scenarios" / f"{scenario_name}.json"
            scenario = json.loads(path.read_text(encoding="utf-8"))
        else:
            scenario = {"name": "live", "description": "Live run started from the server.", "faults": []}
        # Live runs start "now" with a fresh seed; fault timings stay relative to the start.
        scenario["start_time"] = datetime.now().replace(microsecond=0).isoformat()
        scenario["seed"] = self.seed if self.seed is not None else int(time.time()) % 1_000_000
        self.scenario_name = scenario["name"]
        self.sim = Simulation(self.machine_cfg, scenario, self.out_root, standard_cfg=self.standard_cfg)
        self.sim.operator.enabled = auto
        self._debt = 0.0

    def set_speed(self, speed: float) -> None:
        self.speed = min(MAX_SPEED, max(0.1, speed))

    def advance(self, real_dt: float) -> None:
        if self.paused:
            return
        dt = self.sim.clock.dt
        self._debt += real_dt * self.speed
        ticks = int(self._debt / dt)
        self._debt -= ticks * dt
        for _ in range(ticks):
            self.sim.step()

    def state(self) -> dict:
        sim = self.sim
        return {
            **sim.machine.snapshot(),
            "sensors": sim.latest_sensors,
            "live_log": sim.log.query_events("INFO", limit=40),
            "setpoints": sim.machine.setpoints,
            "sim": {
                "run_id": sim.run_id,
                "scenario": self.scenario_name,
                "speed": self.speed,
                "paused": self.paused,
                "auto_operator": sim.operator.enabled,
            },
            "hmi": self.session.view() if self.session else None,
            "operator": {
                "phase": sim.operator.phase,
                "crew": list(sim.operator.names),
            },
            "engineer": sim.engineer_view(),
        }

    def trends(self, minutes: float, max_points: int = 300) -> dict:
        m = self.sim.machine
        r = m.recipe
        cfg = self.machine_cfg
        target = r["target_bead_weight_mg"]
        tol = target * r["weight_tolerance_pct"] / 100.0
        band = cfg["dispenser"]["temp_alarm_band_c"]
        limits = {
            "fixture_vac_kpa": {"hi": cfg["dispenser"]["vacuum_threshold_kpa"]},
            "weight_check_mg": {"lo": target - tol, "hi": target + tol},
            "bead_width_mm": {"lo": r["bead_width_spec_mm"][0], "hi": r["bead_width_spec_mm"][1]},
            "disp_temp_c": {"lo": r["syringe_temp_c"] - band, "hi": r["syringe_temp_c"] + band},
            "disp_pressure_kpa": {},
            "bead_offset_mm": {"hi": cfg["inspection"]["max_bead_offset_mm"]},
        }
        now_ms = m.clock.now.timestamp() * 1000.0
        since_ms = now_ms - minutes * 60_000.0
        return {
            "now": now_ms,
            "since": since_ms,
            "series": {
                name: {"points": m.trends.window(name, since_ms, max_points), "limits": lim}
                for name, lim in limits.items()
            },
        }

    async def run_forever(self, on_frame: Callable[[dict], Awaitable[None]]) -> None:
        last = time.perf_counter()
        last_flush = last
        while True:
            await asyncio.sleep(FRAME_S)
            now = time.perf_counter()
            self.last_frame = now
            self.advance(now - last)
            last = now
            if now - last_flush >= FLUSH_S:
                self.sim.flush()
                last_flush = now
            await on_frame(self.state())

    def close(self) -> None:
        if self.sim:
            self.sim.close()
