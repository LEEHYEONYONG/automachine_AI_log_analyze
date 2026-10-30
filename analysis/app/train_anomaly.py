"""이상 탐지의 평소 모습을 배워 anomaly_profile.json에 저장한다.
analysis는 정답지를 못 보므로, 호스트에서 dev 런의 고장 구간만 뽑아 표준 입력으로 넘긴다.

    python3 eval/normal_periods.py | docker compose exec -T analysis python -m app.train_anomaly
"""
import json
import sys
from datetime import datetime, timedelta

from sqlalchemy import text

from .anomaly import PROFILE_FILE, features, learn
from .database import SessionLocal

MARGIN = timedelta(minutes=10)   # 고장이 끝난 직후는 값이 아직 덜 돌아왔을 수 있어서 빼고 배움


def in_fault(ts, spans):
    return any(s <= ts <= e for s, e in spans)


def main():
    runs = json.load(sys.stdin)
    db = SessionLocal()
    rows = []
    for r in runs:
        spans = [(datetime.fromisoformat(f["start"]),
                  datetime.fromisoformat(f["end"]) + MARGIN if f["end"] else datetime.max)
                 for f in r["faults"]]
        parts = db.execute(text("""
            SELECT start_time, recipe, bead_width_mm, bead_offset_mm, disp_pressure_kpa, ng_reason
            FROM production WHERE run_id = :r ORDER BY start_time
        """), {"r": r["run_id"]}).mappings().all()
        sensors = db.execute(text("""
            SELECT ts, mode, disp_valve_open, fixture_vac_kpa
            FROM sensor_trend WHERE run_id = :r ORDER BY ts
        """), {"r": r["run_id"]}).mappings().all()
        rows += [(recipe, values) for ts, recipe, values in features(parts, sensors) if not in_fault(ts, spans)]

    profile = learn(rows)
    PROFILE_FILE.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"런 {len(runs)}개에서 배움 → {PROFILE_FILE.name}")
    for recipe, p in profile.items():
        print(f"  {recipe}: 정상 제품 {p['samples']}개")


if __name__ == "__main__":
    main()
