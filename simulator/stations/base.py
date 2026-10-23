from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Iterator

from simulator.alarms import ALARMS, MachineAlarm

if TYPE_CHECKING:
    from simulator.machine import Machine
    from simulator.workpiece import Workpiece


class StationState(str, Enum):
    IDLE = "IDLE"    # empty, ready to receive a workpiece
    BUSY = "BUSY"    # running its process sequence
    DONE = "DONE"    # finished, waiting for the next station to take the workpiece
    ALARM = "ALARM"  # stopped until the operator resets


class Station:
    """A station runs its process as a generator that yields step durations in seconds.

    Writing the sequence as straight-line code keeps it close to how a PLC step
    sequence reads, while this class handles timing, step logging and alarms.
    """

    name = "STATION"
    transfer_s = 1.0  # conveyor time to receive a workpiece from the previous station

    def __init__(self, machine: Machine, cfg: dict):
        self.m = machine
        self.cfg = cfg
        self.state = StationState.IDLE
        self.wp: Workpiece | None = None
        self.step = ""
        self._step_s = 0.0
        self._proc: Iterator[float] | None = None
        self._wait = 0.0

    def view(self) -> dict:
        """What the HMI and 3D viewer need to draw this station."""
        progress = min(1.0, max(0.0, 1.0 - self._wait / self._step_s)) if self.step and self._step_s else 0.0
        return {
            "name": self.name,
            "state": self.state.value,
            "step": self.step,
            "step_s": round(self._step_s, 3) if self.step else 0.0,
            "progress": round(progress, 3),
            "wp": self.wp.wp_id if self.wp else None,
            "judge": self.wp.judge if self.wp else None,
        }

    def can_accept(self) -> bool:
        return self.state is StationState.IDLE and self.wp is None

    def accept(self, wp: Workpiece | None) -> None:
        self.wp = wp
        self._begin(transfer=True)

    def release(self) -> Workpiece | None:
        wp, self.wp = self.wp, None
        self.state = StationState.IDLE
        return wp

    def abort_if_empty(self) -> None:
        """Drop a sequence that has not taken a part yet (e.g. still waiting for upstream)."""
        if self.state is StationState.BUSY and self.wp is None:
            self._end_step()
            self._proc = None
            self.state = StationState.IDLE
            self.step = ""

    def update(self, dt: float) -> None:
        if self.state is not StationState.BUSY:
            return
        self._wait -= dt
        while self._wait <= 0 and self.state is StationState.BUSY:
            self._end_step()
            try:
                self._wait += next(self._proc)
            except StopIteration:
                self.state = StationState.DONE
            except MachineAlarm as alarm:
                self.state = StationState.ALARM
                self.m.raise_alarm(self, alarm)

    def on_reset(self, code: str) -> None:
        """Recover after the operator resets an alarm this station raised."""
        policy = ALARMS[code].on_reset
        if policy == "retry":
            self._begin(transfer=False)
        elif policy == "scrap":
            if self.wp is not None:
                self.m.scrap(self.release(), f"SCRAP_{code}")
            self.state = StationState.IDLE
        else:
            self.state = StationState.DONE

    def process(self) -> Iterator[float]:
        raise NotImplementedError

    def motion(self, step: str, nominal_s: float, jitter: float = 0.05, pneumatic: bool = False) -> float:
        """Start a step and return its duration. Air-cylinder strokes slow down when plant air is low."""
        if pneumatic:
            nominal_s *= self.m.physics.cylinder_slowdown()
        self.step = step
        self._step_s = max(0.0, self.m.rng.gauss(nominal_s, nominal_s * jitter))
        return self._step_s

    def log(self, level: str, message: str, **fields) -> None:
        if self.wp is not None:
            fields = {"wp": self.wp.wp_id, **fields}
        self.m.log.event(level, self.name, message, **fields)

    def _begin(self, transfer: bool) -> None:
        self._proc = self._sequence(transfer)
        self.state = StationState.BUSY
        self._wait = 0.0
        self.step = ""

    def _sequence(self, transfer: bool) -> Iterator[float]:
        if transfer and self.transfer_s:
            yield self.motion("TRANSFER_IN", self.transfer_s)
        yield from self.process()

    def _end_step(self) -> None:
        if self.step and self.m.log_steps:
            self.log("DEBUG", f"Step {self.step} done", t=f"{self._step_s:.3f}s")
        self.step = ""
