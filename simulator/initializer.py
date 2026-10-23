"""Initialization (origin return): what a machine does after power-on or manual work before AUTO may start.

It checks safety inputs, brings cylinders and servo axes home in a collision-free order, and decides
what happens to parts still in the line (work in progress). Each stage is timed and logged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

from simulator.manual import InterlockError

if TYPE_CHECKING:
    from simulator.machine import Machine

# Dispenser steps after which the bead has (at least partly) been laid; such a part cannot be redone.
BEAD_STARTED = {"DISPENSE", "DWELL", "RETRACT", "VACUUM_OFF", "LIFT_DOWN"}
HOMING_SEARCH_MM_S = 40.0  # axes look for their home sensor slower than they normally move


class Initializer:
    def __init__(self, machine: Machine):
        self.m = machine
        self.state = "REQUIRED"  # REQUIRED -> RUNNING -> DONE
        self.step = ""
        self._proc: Iterator[float] | None = None
        self._wait = 0.0
        self._step_s = 0.0
        self._elapsed = 0.0
        self._estimate = 1.0

    @property
    def done(self) -> bool:
        return self.state == "DONE"

    def require(self, reason: str) -> None:
        if self.state != "REQUIRED":
            if self.state == "RUNNING":
                self.m.log.event("WARN", "MACHINE", "Initialize aborted", step=self.step)
            self.state = "REQUIRED"
            self._proc = None
            self.step = ""
            self.m.log.event("INFO", "MACHINE", "Initialize required", reason=reason)

    def start(self, clear_parts: bool, by: str) -> None:
        m = self.m
        if self.state == "RUNNING":
            raise InterlockError("이미 원점 복귀 중입니다")
        if m.op_mode != "AUTO":
            raise InterlockError("원점 복귀는 AUTO 모드에서 합니다")
        if m.mode.value == "RUNNING":
            raise InterlockError("운전 중에는 원점 복귀를 할 수 없습니다")
        if m.mode.value == "ALARM":
            raise InterlockError("알람을 먼저 리셋하세요")
        problems = self._safety_problems()
        if problems:
            raise InterlockError("안전 조건 미충족: " + ", ".join(problems))
        m.manual.sync_from_auto()  # where the stopped sequences left the hardware
        self._estimate = self._estimate_s()
        self._elapsed = 0.0
        self._proc = self._sequence(clear_parts, by)
        self._wait = 0.0
        self.state = "RUNNING"
        m.log.event("INFO", "MACHINE", "Initialize start", wip="clear" if clear_parts else "keep", by=by)

    def update(self, dt: float) -> None:
        if self.state != "RUNNING":
            return
        self._elapsed += dt
        self._wait -= dt
        while self._wait <= 0 and self.state == "RUNNING":
            if self.step:
                self.m.log.event("INFO", "MACHINE", f"Initialize step {self.step} done", t=f"{self._step_s:.3f}s")
                self.step = ""
            try:
                self._wait += next(self._proc)
            except StopIteration:
                self.state = "DONE"
                self.m.log.event("INFO", "MACHINE", "Initialize done", t=f"{self._elapsed:.1f}s")

    def view(self) -> dict:
        progress = 1.0 if self.done else min(0.99, self._elapsed / self._estimate) if self.state == "RUNNING" else 0.0
        return {"state": self.state, "step": self.step, "progress": round(progress, 3)}

    # ---- sequence ---------------------------------------------------------------

    def _do(self, step: str, seconds: float) -> float:
        self.step = step
        self._step_s = seconds
        self.m.io.dirty = True
        return seconds

    def _sequence(self, clear_parts: bool, by: str) -> Iterator[float]:
        m = self.m
        slow = m.physics.cylinder_slowdown()
        dev, ax = m.manual.devices, m.manual.axes

        yield self._do("SAFETY_CHECK", 0.2)
        m.dispenser.vacuum_on = False
        m.dispenser.valve_open = False
        m.outfeed.picker_vacuum = False
        yield self._do("VACUUM_OFF", 0.3)
        yield self._do("CYLINDERS_RETRACT", 0.4 * slow)   # pushers back, NG picker up
        yield self._do("LIFTS_DOWN", 0.4 * slow)
        yield self._do("STOPPERS_UP", 0.15 * slow)
        yield self._do("Z_HOME", self._axis_time("DISP_Z"))
        yield self._do("XY_HOME", max(self._axis_time("DISP_X"), self._axis_time("DISP_Y")))
        yield self._do("AUX_AXES_HOME", max(self._axis_time("SCAN_X"), self._axis_time("NG_PICK_Y")))

        for d in dev.values():
            d.position = d.target = d.auto_ready
        for a in ax.values():
            a.position = a.target = a.home_mm
        m.manual.used = False

        yield self._do("WIP_CHECK", 0.3)
        self._handle_work_in_progress(clear_parts, by)

    def _axis_time(self, axis_id: str) -> float:
        """Search for the home sensor, back off, then latch: ~1 s plus the travel at search speed."""
        a = self.m.manual.axes[axis_id]
        return 1.0 + abs(a.position - a.home_mm) / HOMING_SEARCH_MM_S

    def _estimate_s(self) -> float:
        slow = self.m.physics.cylinder_slowdown()
        axes = self._axis_time("DISP_Z") + max(self._axis_time("DISP_X"), self._axis_time("DISP_Y")) \
            + max(self._axis_time("SCAN_X"), self._axis_time("NG_PICK_Y"))
        return 0.2 + 0.3 + 0.95 * slow + axes + 0.3

    def _safety_problems(self) -> list[str]:
        m = self.m
        problems = m.safety_problems()
        if m.physics.air.supply_kpa < m.cfg["air_pressure_switch_kpa"]:
            problems.append("메인 에어 압력 부족")
        return problems

    def _handle_work_in_progress(self, clear_parts: bool, by: str) -> None:
        """Clear: the operator takes every part out. Keep: unfinished stations start over, except a
        dispenser whose bead was already started - that part is judged NG and sent out."""
        m = self.m
        for s in m.stations:
            if clear_parts:
                if s.wp is not None:
                    m.scrap(s.release(), "SCRAP_INIT")
                s.reset_sequence()
                continue
            if s.state.value == "DONE":
                continue
            if s.wp is None:
                s.reset_sequence()
            elif s.name == "INFEED":
                s.finish_now()  # the part is already on the zone; just hand it on
            elif s.name == "DISPENSER" and (s.step in BEAD_STARTED or "bead_weight_mg" in s.wp.hidden):
                s.wp.judge = "NG"
                s.wp.ng_reason = "INIT_INCOMPLETE"
                s.finish_now()
                m.log.event("WARN", s.name, "Part judged NG by initialize", wp=s.wp.wp_id, reason="INIT_INCOMPLETE")
            else:
                s.restart_sequence()
                m.log.event("INFO", s.name, "Sequence restarted by initialize", wp=s.wp.wp_id)
