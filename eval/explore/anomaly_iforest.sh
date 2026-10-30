#!/bin/bash
# 이상 탐지 비교 실험: Isolation Forest. 런 하나씩 빼고 배움. A=정답지 없이 전부(고장 22% 섞임), B=정상 구간만
# 값 7개는 app.anomaly.features 그대로. 간이 채점(고장 구간+10분 안에 울렸나). 결과: z-score보다 못해서 비교로만 남김 (2026-10-30)
# 사용: bash eval/explore/anomaly_iforest.sh ["A|B 기준% 연속"]  예: bash eval/explore/anomaly_iforest.sh "A 1 10"
SHOW=${1:-}
cd ~/projects/automachine_AI_log_analyze || exit 1
python3 - > /tmp/am_z_runs.json <<'EOF'
import csv, json
from pathlib import Path
dev = {(r["scenario"], r["seed"]) for r in csv.DictReader(open("eval/runs.csv")) if r["split"] == "dev"}
out = []
for p in sorted(Path("ground_truth").glob("*/faults.json")):
    t = json.loads(p.read_text())
    if (t["scenario"], str(t["seed"])) not in dev:
        continue
    out.append({"run_id": t["run_id"], "scenario": t["scenario"],
                "faults": [{"type": f["type"], "start": f["injected_at"], "end": f.get("resolved_at")} for f in t["faults"]]})
print(json.dumps(out))
EOF
docker compose cp /tmp/am_z_runs.json analysis:/tmp/am_z_runs.json >/dev/null 2>&1
docker compose exec -T -e SHOW="$SHOW" analysis python - <<'EOF'
import json, os, statistics
from collections import defaultdict
from datetime import datetime, timedelta
import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import text
from app.anomaly import FEATURES, features
from app.database import SessionLocal

MARGIN = timedelta(minutes=10)
runs = json.load(open("/tmp/am_z_runs.json"))
db = SessionLocal()

def span(f):
    s = datetime.fromisoformat(f["start"])
    return s, (datetime.fromisoformat(f["end"]) + MARGIN if f["end"] else datetime.max)

def in_fault(ts, faults):
    return any(s <= ts <= e for s, e in map(span, faults))

# 런별 (시각, 레시피, 값 벡터, 고장 중?)
data = {}
for r in runs:
    parts = db.execute(text("""SELECT start_time, recipe, bead_width_mm, bead_offset_mm, disp_pressure_kpa, ng_reason
                               FROM production WHERE run_id=:r ORDER BY start_time"""), {"r": r["run_id"]}).mappings().all()
    sensors = db.execute(text("""SELECT ts, mode, disp_valve_open, fixture_vac_kpa
                                 FROM sensor_trend WHERE run_id=:r ORDER BY ts"""), {"r": r["run_id"]}).mappings().all()
    data[r["run_id"]] = [(ts, recipe, [v[k] for k in FEATURES], in_fault(ts, r["faults"]))
                         for ts, recipe, v in features(parts, sensors)]

QS = [0.5, 1, 2]          # 배운 데이터 중 점수 하위 몇 %를 "이상" 기준선으로 삼을지
STREAKS = [1, 5, 10]

def scores_for(test, mode):
    """test 런을 뺀 나머지로 레시피별 숲을 만들고, test 런 점수와 기준선(q별)을 돌려준다."""
    train = defaultdict(list)
    for r in runs:
        if r["run_id"] == test:
            continue
        for ts, recipe, x, bad in data[r["run_id"]]:
            if mode == "A" or not bad:
                train[recipe].append(x)
    models = {}
    for recipe, X in train.items():
        X = np.array(X)
        m = IsolationForest(n_estimators=100, random_state=0).fit(X)
        s = m.score_samples(X)                       # 낮을수록 이상 (빨리 혼자 남음)
        models[recipe] = (m, {q: np.percentile(s, q) for q in QS})
    rows = data[test]
    out = []
    by_recipe = defaultdict(list)
    for i, (ts, recipe, x, bad) in enumerate(rows):
        by_recipe[recipe].append(i)
    score = [None] * len(rows)
    for recipe, idx in by_recipe.items():
        if recipe not in models:
            continue                                  # 배운 적 없는 제품
        s = models[recipe][0].score_samples(np.array([rows[i][2] for i in idx]))
        for i, v in zip(idx, s):
            score[i] = v
    return rows, score, {rc: mt[1] for rc, mt in models.items()}

cache = {(r["run_id"], mode): scores_for(r["run_id"], mode) for r in runs for mode in "AB"}

def alarms(run_id, mode, q, n):
    rows, score, cut = cache[(run_id, mode)]
    out, streak = [], 0
    for (ts, recipe, x, bad), s in zip(rows, score):
        hit = s is not None and s < cut[recipe][q]
        streak = streak + 1 if hit else 0
        if streak == n:
            out.append((ts, x, s))
    return out

def evaluate(mode, q, n, show=False):
    found = total = outside = normal_out = 0
    delays, temp = [], []
    for r in runs:
        al = alarms(r["run_id"], mode, q, n)
        line = []
        for f in r["faults"]:
            total += 1
            s, e = span(f)
            h = [a for a in al if s <= a[0] <= e]
            d = (h[0][0] - s).total_seconds() / 60 if h else None
            if h:
                found += 1
                delays.append(d)
            if f["type"] == "temp_sensor_drift":
                temp.append(f"+{d:.0f}분" if h else "놓침")
            line.append(f"{f['type']}@{s:%H:%M} " + (f"+{d:.0f}분" if h else "❌"))
        o = [a for a in al if not in_fault(a[0], r["faults"])]
        outside += len(o)
        normal_out += len(o) if r["scenario"] == "normal" else 0
        if show:
            print(f"{r['run_id'][-6:]} {r['scenario']:<21}" + ("; ".join(line) or "(고장 없음)")
                  + (f" | 헛울림 {len(o)}: " + ", ".join(f"{a[0]:%H:%M}" for a in o) if o else ""))
    return found, total, round(statistics.median(delays)) if delays else "-", outside, normal_out, temp

print("방식  기준%  연속   탐지  지연중앙값  헛울림  normal런  온도센서")
for mode in "AB":
    for q in QS:
        for n in STREAKS:
            f_, t_, d_, o_, no_, tp = evaluate(mode, q, n)
            print(f"  {mode}   {q:>4}  {n:>4}  {f_:>3}/{t_:<3} {d_:>8}  {o_:>6}  {no_:>7}  {', '.join(tp)}")
if os.environ["SHOW"]:
    mode, q, n = os.environ["SHOW"].split()
    print(f"\n## {mode} {q}% 연속 {n}")
    evaluate(mode, float(q) if "." in q else int(q), int(n), True)
EOF
