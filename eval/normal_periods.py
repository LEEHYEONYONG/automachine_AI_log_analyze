"""이상 탐지·원인 분류 학습용: dev 런의 고장 구간과 종류를 JSON으로 출력한다 (test 런은 절대 넣지 않음).
analysis 컨테이너는 정답지를 못 보므로, 정답 전체 대신 "언제 무슨 고장이었나"만 넘긴다.

    python3 eval/normal_periods.py | docker compose exec -T analysis python -m app.train_anomaly
"""
import csv
import json
from pathlib import Path

dev = set()
with Path("eval/runs.csv").open(encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["split"] == "dev":
            dev.add((row["scenario"], row["seed"]))

runs = []
for path in sorted(Path("ground_truth").glob("*/faults.json")):
    truth = json.loads(path.read_text(encoding="utf-8"))
    if (truth["scenario"], str(truth["seed"])) in dev:
        runs.append({"run_id": truth["run_id"],
                     "faults": [{"type": f["type"], "start": f["injected_at"], "end": f.get("resolved_at")}
                                for f in truth["faults"]]})
print(json.dumps(runs))
