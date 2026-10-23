from datetime import datetime, timedelta


class VirtualClock:
    """Simulation time advanced in fixed ticks, independent of wall-clock time."""

    def __init__(self, start: datetime, dt: float = 0.1):
        self.start = start
        self.dt = dt
        self.ticks = 0

    @property
    def elapsed(self) -> float:
        return self.ticks * self.dt

    @property
    def now(self) -> datetime:
        return self.start + timedelta(seconds=self.elapsed)

    def every(self, seconds: float) -> bool:
        return self.ticks % max(1, round(seconds / self.dt)) == 0

    def tick(self) -> None:
        self.ticks += 1
