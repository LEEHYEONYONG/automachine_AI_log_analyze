"""반장의 사건별 원인 판단을 채점한다. 기준은 eval/README.md 7절. 원인은 코드가 정하므로 LLM 없이 몇 분 안에 끝난다.

    python3 eval/score_foreman.py              # dev: 분류 의견은 그 런을 빼고 배운 것을 쓴다
    python3 eval/score_foreman.py --reports 11 # LLM 보고서도 런마다 첫 사건부터 최대 11건 쓰고 수치 검사 결과를 본다
    python3 eval/score_foreman.py --split test # test: 탐정을 다 만든 뒤 한 번만
"""
import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime

from score import API, dev_periods, in_analysis, load_runs, print_report, score

NO_FAULT = "no_fault"
UNKNOWN = "unknown"
LLM_WAIT_S = 600


def call(url, method="GET"):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=LLM_WAIT_S) as res:
        return json.loads(res.read())


def active_faults(truth, at):
    """사건이 시작된 순간 진행 중이던 고장 종류."""
    names = set()
    for f in truth["faults"]:
        start = datetime.fromisoformat(f["injected_at"])
        end = datetime.fromisoformat(f["resolved_at"]) if f.get("resolved_at") else datetime.max
        if start <= at <= end:
            names.add(f["type"])
    return names


def right(name, truth_names):
    """이름이 맞았는가. 진행 중인 고장이 없을 때는 고장이 아니라고 말해야 맞다. 이름이 없으면(None) 고장이 아니라는 뜻이다."""
    if name == UNKNOWN:
        return False
    if not truth_names:
        return name in (None, NO_FAULT)
    return name in truth_names


def fair_answer(fair, run_id, incident):
    """이 런을 빼고 배운 트리가 사건 안의 첫 경보에서 낸 답. (이름, 확신이 낮으면 unknown인 답). 없으면 (None, unknown)."""
    start, end = incident["started_at"], incident["last_at"]
    for c in fair.get(run_id, []):
        if start <= c["detected_at"] <= end:
            return c["evidence"]["best_guess"], c["fault_type"]
    return None, UNKNOWN


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev", choices=["dev", "test"])
    parser.add_argument("--reports", type=int, default=0, help="LLM 보고서를 쓸 사건 수")
    args = parser.parse_args()

    runs, _ = load_runs(args.split)
    fair = {}
    if args.split == "dev":
        fair = json.loads(in_analysis("python", "-m", "app.train_classifier", "--fair", stdin=dev_periods()))

    hits = {"rule": 0, "tree": 0, "code": 0}
    total = unknowns = 0
    answers = {}
    print("| 런 | 시각 | 정답 | 규칙 | 분류 | 코드 판단 |\n|---|---|---|---|---|---|")
    for truth in runs:
        run_id = truth["run_id"]
        answers[run_id] = []
        for incident in call(f"{API}{run_id}/incidents")["incidents"]:
            at = incident["started_at"]
            names = active_faults(truth, datetime.fromisoformat(at))
            rule_name = incident["rule_names"][0] if incident["rule_names"] else None
            if args.split == "dev":
                tree_name, tree_answer = fair_answer(fair, run_id, incident)
            else:
                tree_name = tree_answer = incident.get("tree_guess")
            # 규칙 이름이 있으면 API의 판단 그대로, 없으면 분류 의견이 판단이므로 dev에서는 공정한 의견으로 바꾼다.
            cause = incident["cause"] if rule_name or args.split != "dev" else tree_answer

            total += 1
            hits["rule"] += right(rule_name, names)
            hits["tree"] += right(tree_name, names)
            hits["code"] += right(cause, names)
            unknowns += cause == UNKNOWN
            print(f"| {run_id[-6:]} | {at[11:16]} | {', '.join(sorted(names)) or '없음'} | {rule_name or '-'} "
                  f"| {tree_name or '-'} | {cause} |", flush=True)
            if cause != NO_FAULT:
                answers[run_id].append({"fault_type": cause, "detected_at": at})

    print(f"\n[{args.split}] 사건 {total}개의 원인 이름")
    print(f"- 규칙의 첫 이름 {hits['rule']}/{total}")
    print(f"- 분류 트리 {hits['tree']}/{total}")
    print(f"- 코드 판단 {hits['code']}/{total} (판단 불가 {unknowns}개)")
    print("\n고장 기준 점수 (사후 보고이므로 탐지 표와 섞지 않는다)")
    print_report(score(runs, answers), len(runs))

    if args.reports:
        write_reports(runs, args.reports)


def write_reports(runs, limit):
    """LLM 보고서를 런마다 첫 사건부터 돌아가며 쓴다. 원인은 바뀌지 않으므로 점수가 아니라 설명의 품질을 본다."""
    queue = []
    for truth in runs:
        for i, incident in enumerate(call(f"{API}{truth['run_id']}/incidents")["incidents"]):
            queue.append((i, truth["run_id"], incident["started_at"]))
    queue.sort(key=lambda x: x[0])

    flagged = doubted = astray = 0
    for _, run_id, at in queue[:limit]:
        query = urllib.parse.urlencode({"at": at})
        result = call(f"{API}{run_id}/incidents/report?{query}", "POST")
        flagged += bool(result["unverified_numbers"])
        doubted += bool(result["doubts"])
        astray += bool(result["other_causes"])
        print(f"\n--- {run_id[-6:]} {at[11:16]} {result['cause']} | 함수 {result['tools_called']} "
              f"| 출처 없는 수치 {result['unverified_numbers']} | 다른 고장 {result['other_causes']}\n{result['report']}",
              flush=True)
    print(f"\n보고서 {min(limit, len(queue))}건: 출처 없는 수치 {flagged}건, 다른 고장을 근거로 든 설명 {astray}건, "
          f"의문점을 적은 보고서 {doubted}건")


if __name__ == "__main__":
    main()
