import csv
from datetime import datetime
from pathlib import Path

from simulator.clock import VirtualClock
from simulator.workpiece import PRODUCTION_FIELDS


def fmt_ts(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class CsvSink:
    def __init__(self, path: Path, fieldnames: list[str]):
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=fieldnames, extrasaction="ignore")
        self._writer.writeheader()

    def write(self, row: dict) -> None:
        self._writer.writerow({k: fmt_ts(v) if isinstance(v, datetime) else v for k, v in row.items()})

    def flush(self) -> None:
        self._file.flush()

    def close(self) -> None:
        self._file.close()


class MachineLogger:
    """Writes the files an engineer would pull off a real machine."""

    def __init__(self, log_dir: Path, clock: VirtualClock, sensor_fields: list[str]):
        log_dir.mkdir(parents=True, exist_ok=True)
        self.dir = log_dir
        self.clock = clock
        self._event = open(log_dir / "event.log", "w", encoding="utf-8", newline="\n")
        self._alarm = open(log_dir / "alarm.log", "w", encoding="utf-8", newline="\n")
        self._sensor = CsvSink(log_dir / "sensor_trend.csv", sensor_fields)
        self._production = CsvSink(log_dir / "production.csv", PRODUCTION_FIELDS)

    def timestamp(self) -> str:
        return fmt_ts(self.clock.now)

    def event(self, level: str, unit: str, message: str, **fields) -> None:
        extra = "".join(f" {k}={v}" for k, v in fields.items())
        self._event.write(f"{self.timestamp()} {level:<5} {unit:<10} {message}{extra}\n")

    def alarm(self, action: str, code: str, unit: str, text: str, detail: str = "") -> None:
        suffix = f" | {detail}" if detail else ""
        self._alarm.write(f"{self.timestamp()} {action:<5} {code} {unit:<10} {text}{suffix}\n")

    def sensor(self, row: dict) -> None:
        self._sensor.write(row)

    def production(self, row: dict) -> None:
        self._production.write(row)

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
