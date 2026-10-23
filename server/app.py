from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from faults import FAULT_TYPES
from server.runner import SimRunner
from simulator.alarms import ALARMS
from simulator.operator import ACTION_MINUTES

ROOT = Path(__file__).resolve().parent.parent
MAINTENANCE_ACTIONS = [a for a in ACTION_MINUTES if a not in ("check", "none", "model_change")]


class MaintenanceRequest(BaseModel):
    action: str


class OperatorRequest(BaseModel):
    auto: bool


class SimRequest(BaseModel):
    speed: float | None = None
    paused: bool | None = None


class RunRequest(BaseModel):
    scenario: str | None = None


class RecipeRequest(BaseModel):
    recipe: str


class FaultRequest(BaseModel):
    type: str
    params: dict[str, float] = {}
    delay_min: float = 0.0


def create_app(root: Path = ROOT, out_root: Path | None = None) -> FastAPI:
    runner = SimRunner(root, out_root)
    clients: set[WebSocket] = set()

    async def broadcast(state: dict) -> None:
        for ws in list(clients):
            try:
                await ws.send_json(state)
            except Exception:
                clients.discard(ws)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        runner.new_run()
        task = asyncio.create_task(runner.run_forever(broadcast))
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        runner.close()

    app = FastAPI(title="automachine", lifespan=lifespan)
    app.state.runner = runner

    # All handlers are async so they run on the same event loop as the simulation; no locking needed.

    @app.get("/api/state")
    async def get_state():
        return runner.state()

    @app.get("/api/trends")
    async def get_trends(minutes: float = 60.0):
        return runner.trends(min(max(minutes, 1.0), 24 * 60.0))

    @app.get("/api/meta")
    async def get_meta():
        return {
            "maintenance_actions": MAINTENANCE_ACTIONS,
            "scenarios": runner.scenarios(),
            "recipes": list(runner.machine_cfg["recipes"]),
            "sequences": {
                s.name: [{"step": step, "std_s": std, "condition": cond} for step, std, cond in s.SEQUENCE]
                for s in runner.sim.machine.stations
            },
            "fault_types": {
                name: {
                    "unit": cls.unit,
                    "description": cls.description,
                    "defaults": cls.defaults,
                    "resolved_by": sorted(cls.resolved_by),
                }
                for name, cls in FAULT_TYPES.items()
            },
            "alarm_codes": [vars(a) for a in ALARMS.values()],
        }

    @app.post("/api/machine/{command}")
    async def machine_command(command: Literal["start", "stop", "cycle_stop", "reset"]):
        machine = runner.sim.machine
        if command == "cycle_stop":
            machine.cycle_stop(by="HMI", reason="operator")
        else:
            getattr(machine, command)(by="HMI")
        return runner.state()

    @app.get("/api/logs")
    async def logs(kind: Literal["event", "alarm", "production"] = "event", level: str = "INFO",
                   unit: str = "", q: str = "", limit: int = 200):
        """Recent log entries, newest first (the full history is in the log files)."""
        log = runner.sim.log
        limit = max(1, min(limit, 2000))
        if kind == "event":
            items = log.query_events(level, unit, q, limit)
        else:
            source = log.recent_alarms if kind == "alarm" else log.recent_production
            needle = q.lower()
            items = [r for r in reversed(source)
                     if (not unit or r.get("unit") == unit) and (not needle or needle in str(r).lower())][:limit]
        return {"kind": kind, "items": items, "log_dir": str(log.dir)}

    @app.post("/api/maintenance")
    async def maintenance(req: MaintenanceRequest):
        if req.action not in MAINTENANCE_ACTIONS:
            raise HTTPException(400, f"unknown action: {req.action}")
        machine = runner.sim.machine
        if machine.mode.value == "RUNNING":
            raise HTTPException(409, "stop the machine before maintenance")
        machine.maintenance(req.action, by="HMI")
        machine.log.event("INFO", "MAINT", "Maintenance done", action=req.action, by="HMI")
        return runner.state()

    @app.post("/api/recipe")
    async def model_change(req: RecipeRequest):
        """With the auto operator the change is queued like a planned changeover; otherwise it is immediate."""
        if req.recipe not in runner.machine_cfg["recipes"]:
            raise HTTPException(400, f"unknown recipe: {req.recipe}")
        sim = runner.sim
        if sim.operator.enabled:
            sim.operator.request_model_change(req.recipe)
        elif sim.machine.mode.value == "STOPPED":
            sim.machine.change_recipe(req.recipe, by="HMI")
        else:
            raise HTTPException(409, "stop the machine before a model change")
        return runner.state()

    @app.post("/api/operator")
    async def operator(req: OperatorRequest):
        runner.sim.operator.enabled = req.auto
        return runner.state()

    @app.post("/api/sim")
    async def sim_control(req: SimRequest):
        if req.speed is not None:
            runner.set_speed(req.speed)
        if req.paused is not None:
            runner.paused = req.paused
        return runner.state()

    @app.post("/api/runs")
    async def new_run(req: RunRequest):
        if req.scenario and req.scenario not in runner.scenarios():
            raise HTTPException(400, f"unknown scenario: {req.scenario}")
        runner.new_run(req.scenario)
        return runner.state()

    @app.post("/api/faults")
    async def inject_fault(req: FaultRequest):
        if req.type not in FAULT_TYPES:
            raise HTTPException(400, f"unknown fault type: {req.type}")
        unknown = set(req.params) - set(FAULT_TYPES[req.type].defaults)
        if unknown:
            raise HTTPException(400, f"unknown params: {sorted(unknown)}")
        runner.sim.inject_fault(req.type, req.params, max(0.0, req.delay_min))
        return runner.state()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        clients.add(ws)
        try:
            await ws.send_json(runner.state())
            while True:
                await ws.receive_text()  # keeps the connection open; the client sends nothing yet
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(ws)

    dist = root / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")

    return app


app = create_app()
