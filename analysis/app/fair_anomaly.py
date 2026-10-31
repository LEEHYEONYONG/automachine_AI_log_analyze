"""이상 탐지 공정 채점용: 런마다 그 런을 빼고 배운 평소 모습으로 검사해 답안을 JSON으로 출력한다.
저장된 anomaly_profile.json과 DB는 건드리지 않는다. 채점은 eval/compare.py가 한다.

    python3 eval/normal_periods.py | docker compose exec -T analysis python -m app.fair_anomaly
"""
import json
import sys

from .anomaly import detect_anomaly, learn
from .database import SessionLocal
from .train_anomaly import load_run, normal_rows


def main():
    runs = json.load(sys.stdin)
    db = SessionLocal()
    loaded = {r["run_id"]: load_run(db, r["run_id"]) for r in runs}
    rows = {r["run_id"]: normal_rows(*loaded[r["run_id"]], r["faults"]) for r in runs}

    answers = {}
    for run_id, (parts, sensors) in loaded.items():
        profile = learn([x for other, xs in rows.items() if other != run_id for x in xs])
        candidates = detect_anomaly(run_id, parts, sensors, profile)
        candidates.sort(key=lambda c: c["detected_at"])
        answers[run_id] = candidates
    json.dump(answers, sys.stdout, default=lambda d: d.isoformat())


if __name__ == "__main__":
    main()
