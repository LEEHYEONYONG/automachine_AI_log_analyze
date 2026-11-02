"""탐정(analysis API)의 답안을 정답지(ground_truth)와 비교해 점수를 낸다. 기준은 eval/README.md.

    python eval/score.py              # dev 런 채점 (기본)
    python eval/score.py --split test # test 런 채점: 탐정을 다 만든 뒤 한 번만
    python eval/score.py --clock      # 예전 방식(시계 시간)으로 채점. 생산 시간 방식과 비교할 때
    python eval/score.py --method anomaly  # 이상 탐지 채점: 고장 이름은 안 보고, 고장 중에 울렸는지만 본다
    python eval/score.py --method classify # 경비원 + 원인 분류 채점: 규칙처럼 고장 이름까지 맞혀야 정답
"""
import argparse
import csv
import json
import os
import statistics
import subprocess
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

RUNS_FILE = Path("eval/runs.csv")
# On k8s: ANALYSIS_API=http://127.0.0.1/api/analysis/runs/
API = os.environ.get("ANALYSIS_API", "http://localhost:8101/api/analysis/runs/")
WINDOW_MIN = 60


def running_periods(run_id):
    """event.log의 Mode change 기록으로 장비가 RUNNING이던 구간 목록을 만든다."""
    periods, since = [], None
    with (Path("logs") / run_id / "event.log").open(encoding="utf-8") as f:
        for line in f:
            if "Mode change mode=" not in line:
                continue
            ts = datetime.fromisoformat(line[:23])
            running = "mode=RUNNING" in line
            if running and since is None:
                since = ts
            elif not running and since is not None:
                periods.append((since, ts))
                since = None
    if since is not None:
        periods.append((since, datetime.max))
    return periods


def minutes_between(periods, a, b, clock=False):
    """a~b 사이의 경과 시간(분). 생산 시간 방식이면 장비가 RUNNING이던 시간만 센다."""
    if clock:
        return (b - a).total_seconds() / 60
    return sum(max(0.0, (min(b, e) - max(a, s)).total_seconds()) for s, e in periods) / 60


def load_runs(split):
    """채점할 런: runs.csv의 (scenario, seed) → ground_truth 폴더. (정답지 목록, runs.csv 줄 수)를 돌려준다."""
    wanted = set()
    with RUNS_FILE.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["split"] == split:
                wanted.add((row["scenario"], row["seed"]))

    runs = []
    for path in sorted(Path("ground_truth").glob("*/faults.json")):
        truth = json.loads(path.read_text(encoding="utf-8"))
        if (truth["scenario"], str(truth["seed"])) in wanted:
            runs.append(truth)
    return runs, len(wanted)


def in_analysis(*command, stdin=None):
    """analysis 컨테이너 안에서 명령을 실행해 출력을 돌려준다. k8s에서는
    ANALYSIS_EXEC="kubectl -n automachine exec -i deploy/analysis --" 를 설정한다."""
    prefix = os.environ.get("ANALYSIS_EXEC", "docker compose exec -T analysis").split()
    return subprocess.run([*prefix, *command], input=stdin, check=True, capture_output=True).stdout


def dev_periods():
    """dev 런의 고장 구간과 종류. 학습과 공정 채점의 입력."""
    return subprocess.run(["python3", "eval/normal_periods.py"], check=True, capture_output=True).stdout


def ask_api(run_id, method):
    req = urllib.request.Request(f"{API}{run_id}?method={method}", method="POST")
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())["candidates"]


def score(runs, answers, by_name=True, clock=False):
    """answers: {run_id: 후보 목록}. by_name=False면 고장 이름은 안 맞춰 본다 (울렸는지만)."""
    def matches(fault, candidate):
        return not by_name or fault["type"] == candidate["fault_type"]

    found = defaultdict(int)      # 종류별 찾은 고장 수
    total = defaultdict(int)      # 종류별 정답 고장 수
    delays = defaultdict(list)    # 종류별 지연(분)
    false_alarms = defaultdict(int)
    details = []
    unknown = 0

    for truth in runs:
        run_id = truth["run_id"]
        periods = running_periods(run_id)

        faults = []
        for f in truth["faults"]:
            start = datetime.fromisoformat(f["injected_at"])
            end = datetime.fromisoformat(f["resolved_at"]) if f.get("resolved_at") else datetime.max
            faults.append({"type": f["type"], "start": start, "end": end, "detected": None})
            total[f["type"]] += 1

        misses = []
        miss_start = {}                                   # 종류별 마지막 오탐 묶음의 시작 시각
        for c in answers[run_id]:                         # 시각 순서
            if by_name and c["fault_type"] == "unknown":  # 모른다는 답은 찾은 것도 오탐도 아니다 (README 3절)
                unknown += 1
                continue
            at = datetime.fromisoformat(c["detected_at"])
            hits = [f for f in faults if matches(f, c)
                    and f["start"] <= at and minutes_between(periods, f["start"], at, clock) <= WINDOW_MIN]
            if not hits and any(matches(f, c) and f["detected"] and at <= f["end"] for f in faults):
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
                    delays[f["type"]].append(minutes_between(periods, f["start"], at, clock))
                    break

        got = ", ".join(f"{f['type']}@{f['start']:%H:%M}" + (f" → {f['detected']:%H:%M} ✅" if f["detected"] else " ❌")
                        for f in faults) or "(고장 없음)"
        details.append(f"{run_id[-6:]} {truth['scenario']:<21} 정답: {got}"
                       + (f"\n{'':29}오탐: " + ", ".join(m + (f" (반복 {n}번)" if n > 1 else "") for m, n in misses)
                          if misses else ""))

    return {"found": found, "total": total, "delays": delays, "false_alarms": false_alarms, "details": details,
            "unknown": unknown, "all_found": sum(found.values()), "all_total": sum(total.values()),
            "all_delays": [x for v in delays.values() for x in v], "all_false": sum(false_alarms.values())}


def print_report(result, run_count):
    found, total, delays, false_alarms = result["found"], result["total"], result["delays"], result["false_alarms"]
    print("\n## 런별")
    print("\n".join(result["details"]))

    print("\n## 고장 종류별")
    print(f"{'종류':<22}{'탐지':>8}{'지연(분, 중앙값)':>18}{'오탐':>6}")
    for t in sorted(set(total) | set(false_alarms)):
        d = f"{statistics.median(delays[t]):.0f}" if delays[t] else "-"
        print(f"{t:<22}{found[t]:>4}/{total[t]:<3}{d:>18}{false_alarms[t]:>6}")

    print("\n## 전체")
    if result["all_total"]:
        print(f"탐지율 {result['all_found']}/{result['all_total']} = {result['all_found'] / result['all_total']:.0%}")
    else:
        print("탐지율 -")
    print(f"지연 중앙값 {statistics.median(result['all_delays']):.0f}분" if result["all_delays"] else "지연 -")
    print(f"오탐 {result['all_false']}개 (런당 {result['all_false'] / run_count:.2f})")
    if result["unknown"]:
        print(f"모른다고 답함 {result['unknown']}개 (점수에 넣지 않음)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev", choices=["dev", "test"])
    parser.add_argument("--clock", action="store_true", help="장비가 멈춘 시간도 포함해 잰다 (10/29 이전 방식)")
    parser.add_argument("--method", default="rule", choices=["rule", "anomaly", "classify"])
    args = parser.parse_args()

    runs, wanted = load_runs(args.split)
    print(f"[{args.split}] {args.method} / 런 {len(runs)}개 / runs.csv {wanted}줄, "
          f"{'시계 시간' if args.clock else '생산 시간(장비가 멈춘 시간 제외)'} 기준")

    answers = {t["run_id"]: ask_api(t["run_id"], args.method) for t in runs}
    print_report(score(runs, answers, by_name=args.method != "anomaly", clock=args.clock), len(runs))


if __name__ == "__main__":
    main()
