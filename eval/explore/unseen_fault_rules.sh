#!/bin/bash
# 처음 보는 고장 시험 (규칙): 고장 T의 규칙을 뺐을 때 다른 규칙이 T 구간에서 울리는지 (이름은 안 봄, 2026-10-30)
# 결과: 규칙 전부 30/31 → 자기 규칙 빼면 6/31. 경비원(anomaly_zscore.sh)은 정상만 배우므로 원래 26/31 그대로
cd ~/projects/automachine_AI_log_analyze || exit 1
python3 - <<'EOF'
import csv, json, urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

MARGIN = timedelta(minutes=10)
dev = {(r["scenario"], r["seed"]) for r in csv.DictReader(open("eval/runs.csv")) if r["split"] == "dev"}
runs = [t for t in (json.loads(p.read_text()) for p in sorted(Path("ground_truth").glob("*/faults.json")))
        if (t["scenario"], str(t["seed"])) in dev]

caught_all, caught_wo, total, who = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(list)
for t in runs:
    req = urllib.request.Request(f"http://localhost:8101/api/analysis/runs/{t['run_id']}?method=rule", method="POST")
    cands = json.loads(urllib.request.urlopen(req).read())["candidates"]
    for f in t["faults"]:
        s = datetime.fromisoformat(f["injected_at"])
        e = datetime.fromisoformat(f["resolved_at"]) + MARGIN if f.get("resolved_at") else datetime.max
        inside = [c for c in cands if s <= datetime.fromisoformat(c["detected_at"]) <= e]
        total[f["type"]] += 1
        caught_all[f["type"]] += bool(inside)
        others = [c for c in inside if c["fault_type"] != f["type"]]     # T의 규칙을 뺐다고 치면
        if others:
            caught_wo[f["type"]] += 1
            first = min(others, key=lambda c: c["detected_at"])
            d = (datetime.fromisoformat(first["detected_at"]) - s).total_seconds() / 60
            who[f["type"]].append(f"{t['run_id'][-6:]} {first['fault_type']} +{d:.0f}분")
        else:
            who[f["type"]].append(f"{t['run_id'][-6:]} ❌")

print(f"{'고장 T':<22}{'규칙 전부':>8}{'T 규칙 빼면':>10}  누가 대신 울렸나")
for k in sorted(total):
    print(f"{k:<22}{caught_all[k]:>4}/{total[k]:<4}{caught_wo[k]:>6}/{total[k]:<4}  " + ", ".join(who[k]))
print(f"\n합계: 규칙 전부 {sum(caught_all.values())}/{sum(total.values())}, "
      f"자기 규칙 빼면 {sum(caught_wo.values())}/{sum(total.values())}")
EOF
