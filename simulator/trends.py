from collections import deque
from datetime import datetime


class TrendStore:
    """Per-part and per-check process values kept in memory for the HMI trend charts."""

    def __init__(self, maxlen: int = 50_000):
        self.maxlen = maxlen
        self._series: dict[str, deque[tuple[float, float]]] = {}

    def add(self, name: str, t: datetime, value: float) -> None:
        self._series.setdefault(name, deque(maxlen=self.maxlen)).append((t.timestamp() * 1000.0, value))

    def window(self, name: str, since_ms: float, max_points: int) -> list[tuple[float, float]]:
        points = [p for p in self._series.get(name, ()) if p[0] >= since_ms]
        if len(points) <= max_points:
            return points
        # Average into equal time buckets so long windows stay light to send.
        t0, t1 = points[0][0], points[-1][0]
        width = (t1 - t0) / max_points or 1.0
        buckets: dict[int, list[float]] = {}
        for t, v in points:
            acc = buckets.setdefault(min(int((t - t0) / width), max_points - 1), [0.0, 0.0, 0])
            acc[0] += t
            acc[1] += v
            acc[2] += 1
        return [(round(s[0] / s[2]), round(s[1] / s[2], 4)) for _, s in sorted(buckets.items())]
