from __future__ import annotations

from collections import Counter, deque
from enum import Enum
from random import Random
from typing import Callable

from simulator.alarms import ALARMS, MachineAlarm
from simulator.clock import VirtualClock
from simulator.logger import MachineLogger
from simulator.io import IoMonitor
from simulator.manual import InterlockError, ManualDevices
from simulator.physics import DispenserPhysics, FixturePhysics, Physics, PlantAir
from simulator.sensors import Sensor
from simulator.stations import Dispenser, Infeed, Inspection, Outfeed, Station, StationState, Vision
from simulator.trends import TrendStore
from simulator.workpiece import Workpiece

# Per-part measurements that feed the HMI trend charts (weight checks are added by the dispenser).
PART_TRENDS = ("fixture_vac_kpa", "disp_pressure_kpa", "disp_temp_c", "bead_width_mm", "bead_offset_mm")


class MachineMode(str, Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    ALARM = "ALARM"


class Machine:
    """The dispensing cell: stations in series, run/stop/reset control, recipes, lots and counters.

    start/stop/reset/maintenance/change_recipe are the same commands the HMI sends.
    """

    def __init__(self, cfg: dict, clock: VirtualClock, log: MachineLogger, rng: Random):
        self.cfg = cfg
        self.machine_id = cfg["machine_id"]
        self.clock = clock
        self.log = log
        self.rng = rng
        self.log_steps = cfg.get("log_steps", True)
        self.current_operator = "OP"

        # `recipe` is the validated recipe; `setpoints` is what is actually loaded and can be mistyped.
        self.recipe = self._load_recipe(cfg["default_recipe"])
        self.setpoints = dict(self.recipe)

        capacity = cfg["dispenser"]["syringe_capacity_ml"]
        temp = self.recipe["syringe_temp_c"]
        self.physics = Physics(
            air=PlantAir(nominal_kpa=cfg["plant"]["nominal_air_kpa"]),
            fixture=FixturePhysics(),
            dispenser=DispenserPhysics(temp_setpoint_c=temp, temp_true_c=temp,
                                       syringe_capacity_ml=capacity, syringe_level_ml=capacity,
                                       thickening_per_h=cfg["dispenser"]["thickening_per_h"]),
        )
        self.sensors = {
            "fixture_vac": Sensor(noise_std=0.4, decimals=1),
            "disp_pressure": Sensor(noise_std=0.8, decimals=1),
            "disp_temp": Sensor(noise_std=0.05, decimals=2),
            "nozzle_height": Sensor(noise_std=0.003, decimals=3),
        }

        self.infeed = Infeed(self, cfg["infeed"])
        self.vision = Vision(self, cfg["vision"])
        self.dispenser = Dispenser(self, cfg["dispenser"])
        self.inspection = Inspection(self, cfg["inspection"])
        self.outfeed = Outfeed(self, cfg["outfeed"])
        self.stations: list[Station] = [self.infeed, self.vision, self.dispenser, self.inspection, self.outfeed]

        self.mode = MachineMode.STOPPED
        self.active_alarm: tuple[Station | None, MachineAlarm] | None = None
        self.maintenance_listeners: list[Callable[[str, str], None]] = []
        self.counts: Counter[str] = Counter()
        self.alarm_counts: Counter[str] = Counter()
        self.alarm_history: deque[dict] = deque(maxlen=200)  # newest first
        self.trends = TrendStore()
        self.mode_seconds: Counter[str] = Counter()  # RUNNING / STOPPED / ALARM, plus STARVED and BLOCKED
        self._finished_at: deque[float] = deque(maxlen=2000)
        self.op_mode = "AUTO"  # AUTO: sequences run on START. MANUAL: devices are moved one by one.
        self.manual = ManualDevices(self)
        self.io = IoMonitor(self)
        self.io.update(force=True)  # initial read so the I/O screen is filled before the first tick
        self._cycle_stop = False

        self._lot_id: str | None = None
        self._lot_no = 0
        self._lot_seq = 0
        self._lots: dict[str, Counter[str]] = {}

    # ---- commands -------------------------------------------------------------

    def start(self, by: str) -> None:
        if self.mode is MachineMode.ALARM:
            self.log.event("WARN", "MACHINE", "Start rejected: alarm active", by=by)
            return
        if self.op_mode != "AUTO":
            self.log.event("WARN", "MACHINE", "Start rejected: not in AUTO mode", by=by)
            return
        self._cycle_stop = False
        self.mode = MachineMode.RUNNING
        self.log.event("INFO", "MACHINE", "Mode change", mode=self.mode.value, by=by)

    def stop(self, by: str) -> None:
        if self.mode is MachineMode.RUNNING:
            self._cycle_stop = False
            self.mode = MachineMode.STOPPED
            self.log.event("INFO", "MACHINE", "Mode change", mode=self.mode.value, by=by)

    def set_op_mode(self, op_mode: str, by: str) -> None:
        """Switch AUTO/MANUAL. Raises InterlockError with the reason when the switch is not allowed."""
        if op_mode == self.op_mode:
            return
        if op_mode == "MANUAL":
            if self.mode is MachineMode.RUNNING:
                raise InterlockError("운전 중에는 MANUAL로 바꿀 수 없습니다. 먼저 정지하세요")
            self.manual.sync_from_auto()
        elif op_mode == "AUTO":
            not_ready = self.manual.not_ready_for_auto()
            if not_ready:
                raise InterlockError("자동 운전 원위치가 아닌 장치가 있습니다: " + ", ".join(not_ready))
        else:
            raise InterlockError(f"알 수 없는 모드: {op_mode}")
        self.op_mode = op_mode
        self.log.event("INFO", "MACHINE", "Operation mode change", op_mode=op_mode, by=by)

    def manual_command(self, action, *args, by: str) -> None:
        """Run a manual-mode command, logging interlock refusals like a real HMI would."""
        if self.op_mode != "MANUAL":
            raise InterlockError("MANUAL 모드에서만 수동 조작을 할 수 있습니다")
        try:
            action(*args, by=by)
        except InterlockError as e:
            self.log.event("WARN", "MACHINE", "Interlock", reason=f"[{e}]", by=by)
            raise

    def cycle_stop(self, by: str, reason: str) -> None:
        """Stop feeding new parts and stop once the line is empty (used for breaks and changeovers)."""
        if self.mode is MachineMode.RUNNING and not self._cycle_stop:
            self._cycle_stop = True
            self.log.event("INFO", "MACHINE", "Cycle stop requested", reason=reason, by=by)

    def reset(self, by: str) -> None:
        if self.active_alarm is None:
            return
        station, alarm = self.active_alarm
        self.active_alarm = None
        self.mode = MachineMode.STOPPED
        adef = ALARMS[alarm.code]
        if self.alarm_history and self.alarm_history[0]["cleared_at"] is None:
            self.alarm_history[0]["cleared_at"] = self.log.timestamp()
        self.log.alarm("CLEAR", alarm.code, station.name if station else "MACHINE", adef.text)
        self.log.event("INFO", "MACHINE", "Alarm reset", code=alarm.code, by=by)
        if station:
            station.on_reset(alarm.code)

    def maintenance(self, action: str, by: str) -> None:
        """Apply the physical effect of an operator/engineer action."""
        p = self.physics
        d = p.dispenser
        if action == "empty_ng_buffer":
            self.outfeed.ng_count = 0
        elif action == "replace_syringe":
            d.syringe_level_ml = d.syringe_capacity_ml
            d.material_viscosity = self.rng.gauss(1.0, 0.02)
            d.bubbles = 0
            self.dispenser.syringe_installed_at = self.clock.now
            self.dispenser.need_weight_check = True
        elif action == "purge":
            d.bubbles = 0
            d.syringe_level_ml = max(0.0, d.syringe_level_ml - 0.3)
            self.dispenser.need_weight_check = True
        elif action == "nozzle_clean":
            d.nozzle_open_ratio = 1.0
            d.tip_buildup = 0.0
            self.dispenser.need_weight_check = True
        elif action == "needle_calibration":
            d.needle_z_offset_mm = 0.0
            d.needle_xy_offset_mm = 0.0
            self.dispenser.need_weight_check = True
        elif action == "replace_vacuum_pad":
            p.fixture.leak_ratio = 0.0
        elif action == "call_engineer":
            self.sensors["disp_temp"].offset = 0.0
            d.nozzle_open_ratio = 1.0
            d.tip_buildup = 0.0
            d.needle_z_offset_mm = 0.0
            d.needle_xy_offset_mm = 0.0
            self._restore_setpoints(by)
            self.dispenser.need_weight_check = True
        self.log.event("INFO", "MAINT", "Maintenance start", action=action, by=by)
        for listener in self.maintenance_listeners:
            listener(action, by)

    def change_recipe(self, name: str, by: str) -> None:
        """Model changeover: load another recipe, new parts and a fresh lot."""
        if self._lot_id and self._lots.get(self._lot_id):
            lot = self._lots.pop(self._lot_id)
            self.log.event("INFO", "MACHINE", "Lot end", lot=self._lot_id, ok=lot["OK"], ng=lot["NG"])
        self.recipe = self._load_recipe(name)
        self.setpoints = dict(self.recipe)
        self._lot_id = None
        self.dispenser.need_weight_check = True
        self.log.event("INFO", "MACHINE", "Model change", recipe=name, by=by)
        for listener in self.maintenance_listeners:
            listener("model_change", by)

    def set_param(self, param: str, value: float, by: str) -> None:
        old = self.setpoints[param]
        self.setpoints[param] = value
        self.log.event("INFO", "HMI", "Recipe parameter changed", recipe=self.recipe["name"],
                       param=param, old=old, new=value, by=by)

    # ---- called by stations ---------------------------------------------------

    def raise_alarm(self, station: Station | None, alarm: MachineAlarm) -> None:
        adef = ALARMS[alarm.code]
        unit = station.name if station else "MACHINE"
        self.mode = MachineMode.ALARM
        self._cycle_stop = False
        self.active_alarm = (station, alarm)
        self.alarm_counts[alarm.code] += 1
        self.alarm_history.appendleft({
            "set_at": self.log.timestamp(), "cleared_at": None,
            "code": alarm.code, "unit": unit, "text": adef.text, "detail": alarm.detail,
        })
        self.log.alarm("SET", alarm.code, unit, adef.text, alarm.detail)
        if station:
            station.log("ALARM", f"{alarm.code} {adef.text}", detail=f"[{alarm.detail}]")
        else:
            self.log.event("ALARM", "MACHINE", f"{alarm.code} {adef.text}", detail=f"[{alarm.detail}]")
        self.log.event("INFO", "MACHINE", "Mode change", mode=self.mode.value)

    def new_workpiece(self) -> Workpiece:
        if self._lot_id is None or self._lot_seq >= self.cfg["lot_size"]:
            self._lot_no += 1
            self._lot_seq = 0
            self._lot_id = f"L{self.clock.now:%y%m%d}-{self._lot_no:03d}"
            self._lots[self._lot_id] = Counter()
            self.log.event("INFO", "MACHINE", "Lot start", lot=self._lot_id, recipe=self.recipe["name"])
        self._lot_seq += 1
        return Workpiece(f"{self._lot_id}-{self._lot_seq:04d}", self._lot_id, self.recipe["name"], self.clock.now)

    def scrap(self, wp: Workpiece, reason: str) -> None:
        wp.judge = "NG"
        wp.ng_reason = reason
        self.log.event("WARN", "MACHINE", "Part removed by operator", wp=wp.wp_id, reason=reason)
        self._record(wp)

    # ---- simulation -----------------------------------------------------------

    def step(self) -> None:
        modes = (self.mode, self.op_mode)
        self._step()
        # I/O is only re-read when something may have changed (plus once a second for slow inputs like air).
        if (self.mode, self.op_mode) != modes:
            self.io.dirty = True
        self.io.update(force=self.clock.every(1.0))

    def _step(self) -> None:
        dt = self.clock.dt
        p = self.physics
        p.air.update(dt, self.rng)
        p.update_air_users(self.setpoints["dispense_pressure_kpa"])
        p.dispenser.temp_setpoint_c = self.setpoints["syringe_temp_c"]
        p.dispenser.syringe_age_h = (self.clock.now - self.dispenser.syringe_installed_at).total_seconds() / 3600.0
        p.dispenser.update(dt, self.sensors["disp_temp"].offset)
        self.mode_seconds[self.mode.value] += dt
        if self.op_mode == "MANUAL":
            self.manual.update(dt)
        if self.mode is not MachineMode.RUNNING:
            return
        if self.infeed.step == "WAIT_UPSTREAM":
            self.mode_seconds["STARVED"] += dt
        if self.outfeed.step == "WAIT_DOWNSTREAM":
            self.mode_seconds["BLOCKED"] += dt

        switch = self.cfg["air_pressure_switch_kpa"]
        if p.air.supply_kpa < switch:
            self.raise_alarm(None, MachineAlarm("E9001", f"air<{switch:.0f}kPa"))
            return

        # Move parts downstream first so a station emptied this tick can take the next part.
        last = len(self.stations) - 1
        for i in range(last, -1, -1):
            station = self.stations[i]
            if station.state is not StationState.DONE:
                continue
            if i == last:
                self._record(station.release())
            elif self.stations[i + 1].can_accept():
                self.stations[i + 1].accept(station.release())
        if self._cycle_stop:
            self.infeed.abort_if_empty()  # stop asking upstream for another part
        elif self.infeed.can_accept():
            self.infeed.accept(None)

        for station in self.stations:
            if self.mode is not MachineMode.RUNNING:
                break
            station.update(dt)

        if self._cycle_stop and all(s.state is StationState.IDLE for s in self.stations):
            self._cycle_stop = False
            self.mode = MachineMode.STOPPED
            self.log.event("INFO", "MACHINE", "Mode change", mode=self.mode.value, by="CYCLE_STOP")

    def snapshot(self) -> dict:
        """Current state for the HMI / 3D viewer."""
        return {
            "time": self.log.timestamp(),
            "machine_id": self.machine_id,
            "recipe": self.recipe["name"],
            "mode": self.mode.value,
            "op_mode": self.op_mode,
            "manual": self.manual.view() if self.op_mode == "MANUAL" else None,
            "cycle_stop": self._cycle_stop,
            "alarm": self.alarm_history[0] if self.active_alarm else None,
            "alarm_history": list(self.alarm_history)[:20],
            "lot": self._lot_id,
            "counts": {"OK": self.counts["OK"], "NG": self.counts["NG"]},
            "ng_buffer": self.outfeed.ng_count,
            "ng_buffer_capacity": self.cfg["outfeed"]["ng_buffer_capacity"],
            "syringe_level_pct": round(self.dispenser.level_pct, 1),
            "syringe_age_min": round(self.physics.dispenser.syringe_age_h * 60),
            "stations": [s.view() for s in self.stations],
            "fixture_vacuum_on": self.dispenser.vacuum_on,
            "ng_picker_vacuum_on": self.outfeed.picker_vacuum,
            "dispenser_valve_open": self.dispenser.valve_open,
            "metrics": self.metrics(),
        }

    def metrics(self) -> dict:
        """Production KPIs an operator expects on the HMI."""
        now = self.clock.now
        hour_ago = now.timestamp() - 3600.0
        uph = sum(1 for t in self._finished_at if t >= hour_ago)
        recent = list(self._finished_at)[-21:]
        tact = (recent[-1] - recent[0]) / (len(recent) - 1) if len(recent) > 1 else None
        return {
            "uph": uph,
            "tact_s": round(tact, 2) if tact else None,
            "seconds": {k: round(v) for k, v in self.mode_seconds.items()},
        }

    def _load_recipe(self, name: str) -> dict:
        return {**self.cfg["recipes"][name], "name": name}

    def _restore_setpoints(self, by: str) -> None:
        for param, value in self.recipe.items():
            if self.setpoints.get(param) != value:
                self.set_param(param, value, by)

    def _record(self, wp: Workpiece) -> None:
        now = self.clock.now
        self._finished_at.append(now.timestamp())
        self.log.production(wp.production_row(now))
        for name in PART_TRENDS:
            if name in wp.data:
                self.trends.add(name, now, wp.data[name])
        self.counts[wp.judge] += 1
        lot = self._lots.get(wp.lot_id)
        if lot is None:
            return
        lot[wp.judge] += 1
        if lot.total() == self.cfg["lot_size"]:
            self.log.event("INFO", "MACHINE", "Lot end", lot=wp.lot_id, ok=lot["OK"], ng=lot["NG"])
            del self._lots[wp.lot_id]
