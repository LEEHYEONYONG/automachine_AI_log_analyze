from __future__ import annotations

from collections import Counter, deque
from enum import Enum
from random import Random
from typing import Callable

from simulator.alarms import ALARMS, MachineAlarm
from simulator.clock import VirtualClock
from simulator.logger import MachineLogger
from simulator.physics import DispenserPhysics, LoaderPhysics, Physics
from simulator.sensors import Sensor
from simulator.stations import Dispenser, Inspection, Loader, Station, StationState, Unloader, Vision
from simulator.trends import TrendStore
from simulator.workpiece import Workpiece


# Per-part measurements that feed the HMI trend charts (weight checks are added by the dispenser).
PART_TRENDS = ("pick_vac_kpa", "disp_pressure_kpa", "disp_temp_c", "bead_width_mm")


class MachineMode(str, Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    ALARM = "ALARM"


class Machine:
    """The dispensing cell: stations in series, run/stop/reset control, lots and counters.

    start/stop/reset/maintenance are the same commands the HMI will send later.
    """

    def __init__(self, cfg: dict, clock: VirtualClock, log: MachineLogger, rng: Random):
        self.cfg = cfg
        self.machine_id = cfg["machine_id"]
        self.recipe = cfg["recipe"]
        self.clock = clock
        self.log = log
        self.rng = rng
        self.log_steps = cfg.get("log_steps", True)

        capacity = cfg["dispenser"]["syringe_capacity_ml"]
        temp = self.recipe["syringe_temp_c"]
        self.physics = Physics(
            loader=LoaderPhysics(),
            dispenser=DispenserPhysics(temp_setpoint_c=temp, temp_true_c=temp,
                                       syringe_capacity_ml=capacity, syringe_level_ml=capacity),
        )
        self.sensors = {
            "loader_vac": Sensor(noise_std=0.4, decimals=1),
            "disp_pressure": Sensor(noise_std=0.8, decimals=1),
            "disp_temp": Sensor(noise_std=0.05, decimals=2),
            "nozzle_height": Sensor(noise_std=0.003, decimals=3),
        }

        self.loader = Loader(self, cfg["loader"])
        self.vision = Vision(self, cfg["vision"])
        self.dispenser = Dispenser(self, cfg["dispenser"])
        self.inspection = Inspection(self, cfg["inspection"])
        self.unloader = Unloader(self, cfg["unloader"])
        self.stations: list[Station] = [self.loader, self.vision, self.dispenser, self.inspection, self.unloader]

        self.mode = MachineMode.STOPPED
        self.active_alarm: tuple[Station, MachineAlarm] | None = None
        self.maintenance_listeners: list[Callable[[str], None]] = []
        self.counts: Counter[str] = Counter()
        self.alarm_counts: Counter[str] = Counter()
        self.alarm_history: deque[dict] = deque(maxlen=50)  # newest first
        self.trends = TrendStore()

        self._lot_id: str | None = None
        self._lot_no = 0
        self._lot_seq = 0
        self._lots: dict[str, Counter[str]] = {}

    # ---- commands -------------------------------------------------------------

    def start(self, by: str) -> None:
        if self.mode is MachineMode.ALARM:
            self.log.event("WARN", "MACHINE", "Start rejected: alarm active", by=by)
            return
        self.mode = MachineMode.RUNNING
        self.log.event("INFO", "MACHINE", "Mode change", mode=self.mode.value, by=by)

    def stop(self, by: str) -> None:
        if self.mode is MachineMode.RUNNING:
            self.mode = MachineMode.STOPPED
            self.log.event("INFO", "MACHINE", "Mode change", mode=self.mode.value, by=by)

    def reset(self, by: str) -> None:
        if self.active_alarm is None:
            return
        station, alarm = self.active_alarm
        self.active_alarm = None
        self.mode = MachineMode.STOPPED
        adef = ALARMS[alarm.code]
        if self.alarm_history and self.alarm_history[0]["cleared_at"] is None:
            self.alarm_history[0]["cleared_at"] = self.log.timestamp()
        self.log.alarm("CLEAR", alarm.code, station.name, adef.text)
        self.log.event("INFO", "MACHINE", "Alarm reset", code=alarm.code, by=by)
        station.on_reset(alarm.code)

    def maintenance(self, action: str, by: str) -> None:
        """Apply the physical effect of an operator/engineer action."""
        p = self.physics
        if action == "supply_magazine":
            self.loader.magazine = self.cfg["loader"]["magazine_capacity"]
        elif action == "swap_output_tray":
            self.unloader.tray_count = 0
        elif action == "replace_syringe":
            p.dispenser.syringe_level_ml = p.dispenser.syringe_capacity_ml
            p.dispenser.material_viscosity = self.rng.gauss(1.0, 0.03)
            self.dispenser.need_weight_check = True
        elif action == "nozzle_clean":
            p.dispenser.nozzle_open_ratio = 1.0
            self.dispenser.need_weight_check = True
        elif action == "replace_pick_pad":
            p.loader.leak_ratio = 0.0
        elif action == "call_engineer":
            self.sensors["disp_temp"].offset = 0.0
            p.dispenser.nozzle_open_ratio = 1.0
            self.dispenser.need_weight_check = True
        self.log.event("INFO", "MAINT", "Maintenance start", action=action, by=by)
        for listener in self.maintenance_listeners:
            listener(action)

    # ---- called by stations ---------------------------------------------------

    def raise_alarm(self, station: Station, alarm: MachineAlarm) -> None:
        adef = ALARMS[alarm.code]
        self.mode = MachineMode.ALARM
        self.active_alarm = (station, alarm)
        self.alarm_counts[alarm.code] += 1
        self.alarm_history.appendleft({
            "set_at": self.log.timestamp(), "cleared_at": None,
            "code": alarm.code, "unit": station.name, "text": adef.text, "detail": alarm.detail,
        })
        self.log.alarm("SET", alarm.code, station.name, adef.text, alarm.detail)
        station.log("ALARM", f"{alarm.code} {adef.text}", detail=f"[{alarm.detail}]")
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
        dt = self.clock.dt
        self.physics.dispenser.update(dt, self.sensors["disp_temp"].offset)
        if self.mode is not MachineMode.RUNNING:
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
        if self.loader.can_accept():
            self.loader.accept(None)

        for station in self.stations:
            if self.mode is not MachineMode.RUNNING:
                break
            station.update(dt)

    def snapshot(self) -> dict:
        """Current state for the HMI / 3D viewer."""
        return {
            "time": self.log.timestamp(),
            "machine_id": self.machine_id,
            "recipe": self.recipe["name"],
            "mode": self.mode.value,
            "alarm": self.alarm_history[0] if self.active_alarm else None,
            "alarm_history": list(self.alarm_history)[:20],
            "lot": self._lot_id,
            "counts": {"OK": self.counts["OK"], "NG": self.counts["NG"]},
            "magazine": self.loader.magazine,
            "magazine_capacity": self.cfg["loader"]["magazine_capacity"],
            "tray_count": self.unloader.tray_count,
            "tray_capacity": self.cfg["unloader"]["tray_capacity"],
            "syringe_level_pct": round(self.dispenser.level_pct, 1),
            "stations": [s.view() for s in self.stations],
            "loader_vacuum_on": self.loader.vacuum_on,
            "dispenser_valve_open": self.dispenser.valve_open,
        }

    def _record(self, wp: Workpiece) -> None:
        now = self.clock.now
        self.log.production(wp.production_row(now))
        for name in PART_TRENDS:
            if name in wp.data:
                self.trends.add(name, now, wp.data[name])
        self.counts[wp.judge] += 1
        lot = self._lots[wp.lot_id]
        lot[wp.judge] += 1
        if lot.total() == self.cfg["lot_size"]:
            self.log.event("INFO", "MACHINE", "Lot end", lot=wp.lot_id, ok=lot["OK"], ng=lot["NG"])
            del self._lots[wp.lot_id]
