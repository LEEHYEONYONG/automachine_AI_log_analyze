#!/bin/bash
# 이상 탐지(z-score) 공정 채점: 시험할 런 하나를 빼고 나머지 dev 런으로 배운 뒤 검사 (런마다 반복)
# 측정값은 |z|>3 연속 N개, 불량 개수는 평소 최대치 초과. 간이 채점(고장 구간+10분 안에 울렸나)이라 score.py와 기준이 조금 다름
# 사용: bash eval/explore/anomaly_zscore.sh [런별로 자세히 볼 N]
SHOW=${1:-0}
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
    faults = [{"type": f["type"], "start": f["injected_at"], "end": f.get("resolved_at")} for f in t["faults"]]
    out.append({"run_id": t["run_id"], "scenario": t["scenario"], "faults": faults})
print(json.dumps(out))
EOF
docker compose cp /tmp/am_z_runs.json analysis:/tmp/am_z_runs.json >/dev/null 2>&1
docker compose exec -T -e SHOW=$SHOW analysis python - <<'EOF'
import bisect, json, os, statistics
from collections import defaultdict, deque
from datetime import datetime, timedelta
from sqlalchemy import text
from app.database import SessionLocal

WINDOW, VAC_WINDOW, Z, MARGIN = 10, 20, 3.0, timedelta(minutes=10)
NG_LOOK = timedelta(minutes=10)
MEASURES = ["bead_width_mm", "bead_offset_mm", "disp_pressure_kpa"]
FEATS = MEASURES + ["vacuum_kpa", "void_10min", "stringing_10min", "ng_10min"]
SHORT = {"bead_width_mm": "폭", "bead_offset_mm": "오프셋", "disp_pressure_kpa": "압력", "vacuum_kpa": "진공",
         "void_10min": "VOID수", "stringing_10min": "STRINGING수", "ng_10min": "불량수"}
runs = json.load(open("/tmp/am_z_runs.json"))
db = SessionLocal()

def span(f):
    s = datetime.fromisoformat(f["start"])
    e = datetime.fromisoformat(f["end"]) + MARGIN if f["end"] else datetime.max
    return s, e

def in_fault(ts, faults):
    return any(s <= ts <= e for s, e in map(span, faults))

def features(run_id):
    """제품마다 값 7개: 측정값은 레시피별 최근 10개 중앙값, 진공은 토출 중 샘플 20개 중앙값, 불량은 최근 10분 개수."""
    parts = db.execute(text("SELECT start_time, recipe, ng_reason, " + ", ".join(MEASURES)
                            + " FROM production WHERE run_id=:r ORDER BY start_time"), {"r": run_id}).mappings().all()
    sens = db.execute(text("""SELECT ts, fixture_vac_kpa FROM sensor_trend
                              WHERE run_id=:r AND mode='RUNNING' AND disp_valve_open=1 ORDER BY ts"""),
                      {"r": run_id}).all()
    sens_ts = [s[0] for s in sens]
    win = defaultdict(lambda: {k: deque(maxlen=WINDOW) for k in MEASURES})
    ng = deque()   # 최근 10분 불량 (시각, 사유)
    for p in parts:
        ts = p["start_time"]
        w = win[p["recipe"]]
        for k in MEASURES:
            if p[k] is not None:
                w[k].append(p[k])
        if p["ng_reason"]:
            ng.append((ts, p["ng_reason"]))
        while ng and ng[0][0] < ts - NG_LOOK:
            ng.popleft()
        i = bisect.bisect_right(sens_ts, ts)
        if i < VAC_WINDOW or not all(len(w[k]) == WINDOW for k in MEASURES):
            continue
        m = {k: statistics.median(w[k]) for k in MEASURES}
        m["vacuum_kpa"] = statistics.median(s[1] for s in sens[i - VAC_WINDOW:i])
        m["void_10min"] = sum(r == "BEAD_VOID" for _, r in ng)
        m["stringing_10min"] = sum(r == "STRINGING" for _, r in ng)
        m["ng_10min"] = len(ng)
        yield ts, p["recipe"], m

data = {r["run_id"]: list(features(r["run_id"])) for r in runs}

COUNTS = ["void_10min", "stringing_10min", "ng_10min"]

def learn(skip_run):
    """skip_run을 뺀 나머지 런의 정상 구간에서 배운다. 측정값은 (평균, 표준편차), 불량 개수는 평소 최대치."""
    normal = defaultdict(list)
    for r in runs:
        if r["run_id"] == skip_run:
            continue
        for ts, recipe, m in data[r["run_id"]]:
            if not in_fault(ts, r["faults"]):
                for k in FEATS:
                    normal[(recipe, k)].append(m[k])
    return {key: max(v) if key[1] in COUNTS else (statistics.mean(v), statistics.pstdev(v))
            for key, v in normal.items()}

profs = {r["run_id"]: learn(r["run_id"]) for r in runs}
print("## 평소 최대치 (레시피 A, 시험 런마다 조금씩 다름)")
for k in COUNTS:
    v = sorted({p[("REAR_HOUSING_ADH_A", k)] for p in profs.values()})
    print(f"  {SHORT[k]:<12} 10분에 최대 {v}개 → 이보다 많으면 울림")

def alarms(run, n):
    """측정값: |z|>3이 n개 연속이면 울림. 불량 개수: 평소 최대치를 넘는 순간 울림."""
    prof = profs[run["run_id"]]
    out, streak = [], defaultdict(int)
    for ts, recipe, m in data[run["run_id"]]:
        for k in FEATS:
            if (recipe, k) not in prof:      # 배운 적 없는 제품: 평소 모습을 모름
                continue
            if k in COUNTS:
                over = m[k] > prof[(recipe, k)]
                streak[k] = streak[k] + 1 if over else 0
                if streak[k] == 1:
                    out.append((ts, k, f"{m[k]}개"))
                continue
            mu, sd = prof[(recipe, k)]
            z = (m[k] - mu) / sd if sd else 0
            streak[k] = streak[k] + 1 if abs(z) > Z else 0
            if streak[k] == n:
                out.append((ts, k, f"z={z:+.1f}"))
    return out

def score(n, show=False):
    found = total = outside = normal_out = 0
    delays, by_type = [], defaultdict(lambda: [0, 0])
    for r in runs:
        al = alarms(r, n)
        line = []
        for f in r["faults"]:
            total += 1
            by_type[f["type"]][1] += 1
            s, e = span(f)
            h = [x for x in al if s <= x[0] <= e]
            if h:
                found += 1
                by_type[f["type"]][0] += 1
                d = (h[0][0] - s).total_seconds() / 60
                delays.append(d)
                line.append(f"{f['type']}@{s:%H:%M} +{d:.0f}분 {SHORT[h[0][1]]} {h[0][2]}")
            else:
                line.append(f"{f['type']}@{s:%H:%M} ❌")
        o = [x for x in al if not in_fault(x[0], r["faults"])]
        outside += len(o)
        normal_out += len(o) if r["scenario"] == "normal" else 0
        if show:
            print(f"{r['run_id'][-6:]} {r['scenario']:<21}" + ("; ".join(line) or "(고장 없음)")
                  + (f" | 헛울림 {len(o)}: " + ", ".join(f"{x[0]:%H:%M} {SHORT[x[1]]}" for x in o) if o else ""))
    return found, total, round(statistics.median(delays)) if delays else "-", outside, normal_out, by_type

print("\n## 연속 개수별")
print(f"{'연속':>4} {'탐지':>7} {'지연중앙값':>6} {'헛울림 전체':>6} {'normal런':>6}")
for n in [1, 5, 10, 20, 30]:
    f_, t_, d_, o_, no_, bt = score(n)
    print(f"{n:>4} {f_:>3}/{t_:<3} {d_:>9} {o_:>10} {no_:>8}")
n = int(os.environ["SHOW"])
if n:
    print(f"\n## 연속 {n}개 런별")
    *_, bt = score(n, True)
    print("\n## 연속 %d개 종류별" % n)
    for t, (a, b) in sorted(bt.items()):
        print(f"  {t:<22} {a}/{b}")
EOF
