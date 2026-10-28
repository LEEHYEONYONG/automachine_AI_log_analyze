"""탐정(analysis API)의 답안을 정답지(ground_truth)와 비교해 점수를 낸다. 기준은 eval/README.md.

    python eval/score.py              # dev 런 채점 (기본)
    python eval/score.py --split test # test 런 채점: 탐정을 다 만든 뒤 한 번만
"""
import argparse
import csv
import json
import statistics
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

RUNS_FILE = Path("eval/runs.csv")
API = "http://localhost:8101/api/analysis/runs/"
WINDOW_MIN = 60

parser = argparse.ArgumentParser()
parser.add_argument("--split", default="dev", choices=["dev", "test"])
args = parser.parse_args()

# 1. 채점할 런: runs.csv의 (scenario, seed) → ground_truth 폴더
wanted = set()
with RUNS_FILE.open(encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["split"] == args.split:
            wanted.add((row["scenario"], row["seed"]))

runs = []
for path in sorted(Path("ground_truth").glob("*/faults.json")):
    truth = json.loads(path.read_text(encoding="utf-8"))
    if (truth["scenario"], str(truth["seed"])) in wanted:
        runs.append(truth)
print(f"[{args.split}] 런 {len(runs)}개 / runs.csv {len(wanted)}줄")

# 2. 런마다 탐정에게 묻고 정답지와 비교
found = defaultdict(int)      # 종류별 찾은 고장 수
total = defaultdict(int)      # 종류별 정답 고장 수
delays = defaultdict(list)    # 종류별 지연(분)
false_alarms = defaultdict(int)
details = []

for truth in runs:
    run_id = truth["run_id"]
    req = urllib.request.Request(API + run_id, method="POST")
    with urllib.request.urlopen(req) as res:
        answer = json.loads(res.read())["candidates"]

    faults = []
    for f in truth["faults"]:
        start = datetime.fromisoformat(f["injected_at"])
        end = datetime.fromisoformat(f["resolved_at"]) if f.get("resolved_at") else datetime.max
        faults.append({"type": f["type"], "start": start, "end": end, "detected": None})
        total[f["type"]] += 1

    misses = []
    miss_start = {}                                   # 종류별 마지막 오탐 묶음의 시작 시각
    for c in answer:                                  # 시각 순서
        at = datetime.fromisoformat(c["detected_at"])
        hits = [f for f in faults if f["type"] == c["fault_type"]
                and f["start"] <= at <= f["start"] + timedelta(minutes=WINDOW_MIN)]
        if not hits and any(f["type"] == c["fault_type"] and f["detected"] and at <= f["end"] for f in faults):
            continue                                  # 이미 맞힌 고장이 아직 진행 중일 때 또 외침 → 무시
        if not hits:                                  # 종류 틀림 / 너무 이름 / 너무 늦음 / 없는 고장
            t = c["fault_type"]
            if t in miss_start and at <= miss_start[t] + timedelta(minutes=WINDOW_MIN):
                misses[-1][1] += 1                    # 같은 오탐 반복은 묶음 하나로
            else:
                miss_start[t] = at
                false_alarms[t] += 1
                misses.append([f"{t}@{at:%H:%M}", 1])
            continue
        for f in hits:                                # 같은 고장을 또 외치면 무시
            if f["detected"] is None:
                f["detected"] = at
                found[f["type"]] += 1
                delays[f["type"]].append((at - f["start"]).total_seconds() / 60)
                break

    got = ", ".join(f"{f['type']}@{f['start']:%H:%M}" + (f" → {f['detected']:%H:%M} ✅" if f["detected"] else " ❌")
                    for f in faults) or "(고장 없음)"
    details.append(f"{run_id[-6:]} {truth['scenario']:<21} 정답: {got}"
                   + (f"\n{'':29}오탐: " + ", ".join(m + (f" (반복 {n}번)" if n > 1 else "") for m, n in misses)
                      if misses else ""))

# 3. 점수표
print("\n## 런별")
print("\n".join(details))

print("\n## 고장 종류별")
print(f"{'종류':<22}{'탐지':>8}{'지연(분, 중앙값)':>18}{'오탐':>6}")
for t in sorted(set(total) | set(false_alarms)):
    d = f"{statistics.median(delays[t]):.0f}" if delays[t] else "-"
    print(f"{t:<22}{found[t]:>4}/{total[t]:<3}{d:>18}{false_alarms[t]:>6}")

all_found, all_total = sum(found.values()), sum(total.values())
all_delays = [x for v in delays.values() for x in v]
all_false = sum(false_alarms.values())
print("\n## 전체")
print(f"탐지율 {all_found}/{all_total} = {all_found / all_total:.0%}" if all_total else "탐지율 -")
print(f"지연 중앙값 {statistics.median(all_delays):.0f}분" if all_delays else "지연 -")
print(f"오탐 {all_false}개 (런당 {all_false / len(runs):.2f})")
