"""logs/<run_id>/ 파일을 PostgreSQL에 적재한다.

    python -m app.ingest                       # LOGS_DIR 아래 모든 실행
    python -m app.ingest 20261030_0800_a2eb37  # 지정한 실행만

같은 실행을 다시 적재하면 기존 행을 지우고 새로 넣는다.
io_trace.csv는 파일로 둔다. ground_truth/는 읽지 않는다(eval/ 전용).
"""
import csv
import json
import re
import sys
from pathlib import Path

from .config import LOGS_DIR
from .database import engine

# 2026-10-30 08:39:23.300 INFO  OPERATOR   Alarm acknowledged code=E2001 by=OP-A
EVENT_RE = re.compile(r"^(\S+ \S+) (\w+)\s+(\S+)\s+(.*)$")
# 2026-10-30 10:26:36.700 SET   E3005 DISPENSER  Weight check out of spec | weight=10.39mg
ALARM_RE = re.compile(r"^(\S+ \S+) (SET|CLEAR)\s+(\S+)\s+(\S+)\s+(.*?)(?: \| (.*))?$")
ATTR_RE = re.compile(r"(\w+)=(\S+)")

PRODUCTION_COLUMNS = {
    "wp_id", "lot_id", "recipe", "start_time", "end_time", "cycle_s",
    "align_dx_mm", "align_dy_mm", "align_score", "fixture_vac_kpa", "vac_retries",
    "disp_pressure_kpa", "disp_temp_c", "nozzle_height_mm", "bead_width_mm",
    "bead_offset_mm", "judge", "ng_reason",
}
SENSOR_COLUMNS = {
    "timestamp", "mode", "fixture_vac_kpa", "disp_pressure_kpa",
    "disp_valve_open", "disp_temp_c", "syringe_level_pct",
}


def attrs_json(text):
    return json.dumps(dict(ATTR_RE.findall(text or "")), ensure_ascii=False)


def load_events(cur, run_id, path):
    skipped = 0
    with cur.copy("COPY events (run_id, ts, level, unit, message, attrs) FROM STDIN") as copy:
        with path.open(encoding="utf-8") as f:
            for line in f:
                m = EVENT_RE.match(line.rstrip("\n"))
                if not m:
                    skipped += 1
                    continue
                ts, level, unit, message = m.groups()
                copy.write_row((run_id, ts, level, unit, message, attrs_json(message)))
    return skipped


def load_alarms(cur, run_id, path):
    """SET과 CLEAR를 짝지어 한 행으로 넣는다. CLEAR가 없으면 아직 발생 중인 알람이다."""
    open_alarms = {}  # code -> rows still waiting for CLEAR
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            m = ALARM_RE.match(line.rstrip("\n"))
            if not m:
                continue
            ts, kind, code, unit, message, detail = m.groups()
            if kind == "SET":
                row = {"code": code, "unit": unit, "set_ts": ts, "clear_ts": None,
                       "message": message, "detail": detail}
                rows.append(row)
                open_alarms.setdefault(code, []).append(row)
            elif open_alarms.get(code):
                open_alarms[code].pop(0)["clear_ts"] = ts
    for r in rows:
        cur.execute(
            "INSERT INTO alarms (run_id, code, unit, set_ts, clear_ts, message, detail, attrs)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (run_id, r["code"], r["unit"], r["set_ts"], r["clear_ts"],
             r["message"], r["detail"], attrs_json(r["detail"])),
        )
    return len(rows)


def load_csv(cur, run_id, path, table, expected, rename=None):
    rename = rename or {}
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        unknown = set(header) - expected
        if unknown:
            raise ValueError(f"{path.name}: 모르는 열 {sorted(unknown)}")
        columns = ", ".join(["run_id"] + [rename.get(h, h) for h in header])
        count = 0
        with cur.copy(f"COPY {table} ({columns}) FROM STDIN") as copy:
            for row in reader:
                if len(row) != len(header):
                    continue    # 돌고 있는 런은 마지막 줄이 쓰이는 도중일 수 있다
                copy.write_row([run_id] + [v if v != "" else None for v in row])
                count += 1
    return count


def load_run(cur, run_dir):
    run_id = run_dir.name
    info = json.loads((run_dir / "machine_info.json").read_text(encoding="utf-8"))

    cur.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
    cur.execute(
        "INSERT INTO runs (run_id, machine_id, start_time, end_time, machine_info)"
        " VALUES (%s, %s, %s, %s, %s)",
        (run_id, info["machine_id"], info["start_time"], info.get("end_time"),
         json.dumps(info, ensure_ascii=False)),
    )
    for a in info.get("alarm_codes", []):
        cur.execute(
            "INSERT INTO alarm_codes (code, unit, text, on_reset) VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (code) DO UPDATE SET unit = EXCLUDED.unit, text = EXCLUDED.text,"
            " on_reset = EXCLUDED.on_reset",
            (a["code"], a["unit"], a["text"], a.get("on_reset")),
        )

    skipped = load_events(cur, run_id, run_dir / "event.log")
    alarms = load_alarms(cur, run_id, run_dir / "alarm.log")
    production = load_csv(cur, run_id, run_dir / "production.csv", "production", PRODUCTION_COLUMNS)
    sensors = load_csv(cur, run_id, run_dir / "sensor_trend.csv", "sensor_trend", SENSOR_COLUMNS,
                       rename={"timestamp": "ts"})
    cur.execute("SELECT count(*) FROM events WHERE run_id = %s", (run_id,))
    events = cur.fetchone()[0]
    note = f" (읽지 못한 줄 {skipped})" if skipped else ""
    print(f"{run_id}: events {events}{note}, alarms {alarms}, production {production}, sensor_trend {sensors}")


def main(run_ids):
    logs = Path(LOGS_DIR)
    if run_ids:
        run_dirs = [logs / r for r in run_ids]
    else:
        run_dirs = sorted(p.parent for p in logs.glob("*/machine_info.json"))
    if not run_dirs:
        print(f"{logs}에 적재할 실행이 없습니다.")
        return
    for run_dir in run_dirs:
        if not (run_dir / "machine_info.json").is_file():
            print(f"{run_dir.name}: machine_info.json이 없어 건너뜁니다.")
            continue
        conn = engine.raw_connection()
        try:
            with conn.driver_connection.cursor() as cur:
                load_run(cur, run_dir)
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    main(sys.argv[1:])
