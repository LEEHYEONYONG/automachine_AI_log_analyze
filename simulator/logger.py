import csv
from collections import deque
from datetime import datetime
from pathlib import Path

from simulator.clock import VirtualClock
from simulator.workpiece import PRODUCTION_FIELDS

LEVELS = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ALARM": 3}


def fmt_ts(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _formatted(row: dict) -> dict:
    return {k: fmt_ts(v) if isinstance(v, datetime) else v for k, v in row.items()}


class CsvSink:
    def __init__(self, path: Path, fieldnames: list[str]):
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=fieldnames, extrasaction="ignore")
        self._writer.writeheader()

    def write(self, row: dict) -> None:
        self._writer.writerow(_formatted(row))

    def flush(self) -> None:
        self._file.flush()

    def close(self) -> None:
        self._file.close()


class MachineLogger:
    """Writes the files an engineer would pull off a real machine.

    The most recent entries are also kept in memory for the HMI's live log and log screens.
    """

    def __init__(self, log_dir: Path, clock: VirtualClock, sensor_fields: list[str]):
        log_dir.mkdir(parents=True, exist_ok=True)
        self.dir = log_dir
        self.clock = clock
        self._event = open(log_dir / "event.log", "w", encoding="utf-8", newline="\n")
        self._alarm = open(log_dir / "alarm.log", "w", encoding="utf-8", newline="\n")
        self._sensor = CsvSink(log_dir / "sensor_trend.csv", sensor_fields)
        self._production = CsvSink(log_dir / "production.csv", PRODUCTION_FIELDS)
        self.recent_events: deque[dict] = deque(maxlen=20000)
        self.recent_alarms: deque[dict] = deque(maxlen=1000)
        self.recent_production: deque[dict] = deque(maxlen=2000)

    def timestamp(self) -> str:
        return fmt_ts(self.clock.now)

    def event(self, level: str, unit: str, message: str, **fields) -> None:
        ts = self.timestamp()
        text = message + "".join(f" {k}={v}" for k, v in fields.items())
        self._event.write(f"{ts} {level:<5} {unit:<10} {text}\n")
        self.recent_events.append({"ts": ts, "level": level, "unit": unit, "text": text})

    def alarm(self, action: str, code: str, unit: str, text: str, detail: str = "") -> None:
        ts = self.timestamp()
        suffix = f" | {detail}" if detail else ""
        self._alarm.write(f"{ts} {action:<5} {code} {unit:<10} {text}{suffix}\n")
        self.recent_alarms.append({"ts": ts, "action": action, "code": code, "unit": unit, "text": text, "detail": detail})

    def sensor(self, row: dict) -> None:
        self._sensor.write(row)

    def production(self, row: dict) -> None:
        self._production.write(row)
        self.recent_production.append(_formatted(row))

    def query_events(self, min_level: str = "INFO", unit: str = "", text: str = "", limit: int = 200) -> list[dict]:
        """Newest first."""
        floor = LEVELS.get(min_level, 1)
        needle = text.lower()
        out = []
        for e in reversed(self.recent_events):
            if LEVELS.get(e["level"], 1) < floor or (unit and e["unit"] != unit):
                continue
            if needle and needle not in e["text"].lower():
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out

    def flush(self) -> None:
        """Make the files readable while a live run is still going."""
        self._event.flush()
        self._alarm.flush()
        self._sensor.flush()
        self._production.flush()

    def close(self) -> None:
        self._event.close()
        self._alarm.close()
        self._sensor.close()
        self._production.close()
