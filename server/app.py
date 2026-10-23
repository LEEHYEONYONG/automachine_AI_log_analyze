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
from server.session import AccessDenied, HmiSession
from simulator.alarms import ALARMS
from simulator.manual import InterlockError
from simulator.recipe import RECIPE_SPEC
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


class InitRequest(BaseModel):
    clear_parts: bool = False


class OpModeRequest(BaseModel):
    mode: Literal["AUTO", "MANUAL"]


class DeviceRequest(BaseModel):
    device: str
    on: bool


class AxisRequest(BaseModel):
    axis: str
    move_to: float | None = None
    jog: float | None = None
    preset: str | None = None


class ForceRequest(BaseModel):
    address: str
    value: bool


class RecipeRequest(BaseModel):
    recipe: str


class EstopRequest(BaseModel):
    pressed: bool


class DoorRequest(BaseModel):
    door: str
    open: bool


class RecipeEditRequest(BaseModel):
    values: dict[str, float | list[float]]


class LoginRequest(BaseModel):
    user: str
    pin: str


class FaultRequest(BaseModel):
    type: str
    params: dict[str, float] = {}
    delay_min: float = 0.0


def create_app(root: Path = ROOT, out_root: Path | None = None, seed: int | None = None,
               live: bool = True) -> FastAPI:
    """live=False skips the real-time loop, so tests can step the simulation from their own thread."""
    runner = SimRunner(root, out_root, seed)
    session = HmiSession(root / "config" / "hmi_users.json")
    runner.session = session
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
        task = asyncio.create_task(runner.run_forever(broadcast)) if live else None
        yield
        if task:
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

    def gate(action: str, detail: str = "") -> None:
        """Refuse an HMI command the logged-in level may not use (403), and log the attempt."""
        try:
            session.require(action, detail)
        except AccessDenied as e:
            runner.sim.log.event("WARN", "HMI", "Access denied", action=detail or action,
                                 role=session.level, by=session.by)
            raise HTTPException(403, str(e)) from None

    @app.post("/api/login")
    async def login(req: LoginRequest):
        try:
            user = session.login(req.user, req.pin)
        except AccessDenied as e:
            runner.sim.log.event("WARN", "HMI", "Login failed", user=req.user)
            raise HTTPException(401, str(e)) from None
        runner.sim.log.event("INFO", "HMI", "Login", user=user["id"], role=user["level"])
        return runner.state()

    @app.post("/api/logout")
    async def logout():
        if session.user:
            runner.sim.log.event("INFO", "HMI", "Logout", user=session.by)
        session.logout()
        return runner.state()

    @app.post("/api/machine/{command}")
    async def machine_command(command: Literal["start", "stop", "cycle_stop", "reset"]):
        gate(command)
        machine = runner.sim.machine
        if command in ("start", "reset") and machine.safety_problems():
            machine.log.event("WARN", "MACHINE", f"{command.capitalize()} rejected: safety",
                              reason=f"[{', '.join(machine.safety_problems())}]", by=session.by)
            raise HTTPException(409, "안전 조건 미충족: " + ", ".join(machine.safety_problems()))
        if command == "cycle_stop":
            machine.cycle_stop(by=session.by, reason="operator")
        else:
            getattr(machine, command)(by=session.by)
        return runner.state()

    def interlocked(fn, *args):
        """Run a machine command and turn an interlock refusal into a 409 the HMI can show."""
        try:
            fn(*args)
        except InterlockError as e:
            raise HTTPException(409, str(e)) from None
        return runner.state()

    # Physical actions: anyone can hit the E-stop, and doors are opened by hand (no login involved).

    @app.post("/api/safety/estop")
    async def estop(req: EstopRequest):
        m = runner.sim.machine
        if req.pressed:
            m.press_estop(by=session.by)
        else:
            m.release_estop(by=session.by)
        return runner.state()

    @app.post("/api/safety/door")
    async def door(req: DoorRequest):
        m = runner.sim.machine
        if req.door not in m.doors_open:
            raise HTTPException(400, f"unknown door: {req.door}")
        m.set_door(req.door, req.open, by="FIELD")
        return runner.state()

    @app.post("/api/initialize")
    async def initialize(req: InitRequest):
        gate("initialize")
        return interlocked(lambda: runner.sim.machine.init.start(req.clear_parts, by=session.by))

    @app.post("/api/opmode")
    async def op_mode(req: OpModeRequest):
        gate("op_mode")
        return interlocked(lambda: runner.sim.machine.set_op_mode(req.mode, by=session.by))

    @app.post("/api/manual/device")
    async def manual_device(req: DeviceRequest):
        gate("manual")
        m = runner.sim.machine
        return interlocked(lambda: m.manual_command(m.manual.set_device, req.device, req.on, by=session.by))

    @app.post("/api/manual/axis")
    async def manual_axis(req: AxisRequest):
        gate("manual")
        m = runner.sim.machine
        if req.jog is not None:
            return interlocked(lambda: m.manual_command(m.manual.jog_axis, req.axis, req.jog, by=session.by))
        target = req.move_to
        if req.preset is not None:
            axis = m.manual.axes.get(req.axis)
            if axis is None or req.preset not in axis.presets:
                raise HTTPException(400, f"unknown preset: {req.preset}")
            target = axis.presets[req.preset]
        if target is None:
            raise HTTPException(400, "give move_to, jog or preset")
        return interlocked(lambda: m.manual_command(m.manual.move_axis, req.axis, target, by=session.by))

    @app.get("/api/io")
    async def io():
        m = runner.sim.machine
        return {"op_mode": m.op_mode, **m.io.view()}

    @app.post("/api/io/force")
    async def io_force(req: ForceRequest):
        """Force an output from the I/O screen (MANUAL only). It drives the device behind the output."""
        gate("io_force")
        m = runner.sim.machine
        signal = next((s for s in m.io.outputs if s.address == req.address), None)
        if signal is None or signal.device is None:
            raise HTTPException(400, f"{req.address} cannot be forced")
        on = (not req.value) if signal.invert else req.value
        interlocked(lambda: m.manual_command(m.manual.set_device, signal.device, on, by=session.by))
        return {"op_mode": m.op_mode, **m.io.view()}

    @app.post("/api/manual/home_all")
    async def manual_home_all():
        gate("manual")
        m = runner.sim.machine
        return interlocked(lambda: m.manual_command(m.manual.home_all, by=session.by))

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
        gate("maintenance", req.action)
        machine = runner.sim.machine
        if machine.mode.value == "RUNNING":
            raise HTTPException(409, "stop the machine before maintenance")
        machine.maintenance(req.action, by=session.by)
        machine.log.event("INFO", "MAINT", "Maintenance done", action=req.action, by=session.by)
        return runner.state()

    @app.get("/api/recipes")
    async def recipes():
        m = runner.sim.machine
        history = [e for e in m.log.query_events("INFO", text="Recipe", limit=500)
                   if e["text"].startswith(("Recipe edited", "Recipe parameter changed"))
                   or e["text"].startswith("Model change ")][:50]
        return {
            "current": m.recipe["name"],
            "spec": RECIPE_SPEC,
            "recipes": m.recipes,
            "setpoints": m.setpoints,
            "history": history,
        }

    @app.post("/api/recipes/{name}")
    async def edit_recipe(name: str, req: RecipeEditRequest):
        gate("recipe_edit")
        m = runner.sim.machine
        try:
            changed = m.edit_recipe(name, req.values, by=session.by)
        except InterlockError as e:
            raise HTTPException(400, str(e)) from None
        return {"changed": changed, **(await recipes())}

    @app.post("/api/recipes/{name}/load")
    async def load_recipe(name: str):
        """Model change from the HMI: immediate, machine stopped, AUTO mode."""
        gate("recipe_load")
        m = runner.sim.machine
        if name not in m.recipes:
            raise HTTPException(400, f"unknown recipe: {name}")
        if m.mode.value != "STOPPED" or m.op_mode != "AUTO":
            raise HTTPException(409, "장비가 정지한 AUTO 상태에서만 레시피를 로드할 수 있습니다")
        m.change_recipe(name, by=session.by)
        return await recipes()

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
