from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

from simulator.simulation import Simulation

FRAME_S = 0.1          # how often state is pushed to the browser
FLUSH_S = 1.0          # how often log files are flushed to disk
MAX_SPEED = 1000.0


class SimRunner:
    """Advances a Simulation in step with wall-clock time, scaled by `speed`."""

    def __init__(self, root: Path, out_root: Path | None = None):
        self.root = root
        self.out_root = out_root or root
        self.machine_cfg = json.loads((root / "config" / "machine.json").read_text(encoding="utf-8"))
        self.sim: Simulation | None = None
        self.scenario_name = "live"
        self.speed = 1.0
        self.paused = False
        self._debt = 0.0

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
        scenario["seed"] = int(time.time()) % 1_000_000
        self.scenario_name = scenario["name"]
        self.sim = Simulation(self.machine_cfg, scenario, self.out_root)
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
            "sim": {
                "run_id": sim.run_id,
                "scenario": self.scenario_name,
                "speed": self.speed,
                "paused": self.paused,
                "auto_operator": sim.operator.enabled,
            },
            "engineer": sim.engineer_view(),
        }

    async def run_forever(self, on_frame: Callable[[dict], Awaitable[None]]) -> None:
        last = time.perf_counter()
        last_flush = last
        while True:
            await asyncio.sleep(FRAME_S)
            now = time.perf_counter()
            self.advance(now - last)
            last = now
            if now - last_flush >= FLUSH_S:
                self.sim.flush()
                last_flush = now
            await on_frame(self.state())

    def close(self) -> None:
        if self.sim:
            self.sim.close()
