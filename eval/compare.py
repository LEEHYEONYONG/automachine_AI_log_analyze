"""규칙과 경비원을 같은 채점 기준(eval/README.md)으로 비교한 표를 낸다.

    python3 eval/compare.py              # dev: 경비원은 런 하나씩 빼고 배워서 공정하게 채점
    python3 eval/compare.py --split test # test: 탐정을 다 만든 뒤 한 번만. 경비원은 dev로 배운 평소 모습 그대로
"""
import argparse
import json
import statistics
import subprocess

from score import ask_api, load_runs, score


def fair_guard_answers():
    """dev 경비원 답안: 시험 볼 런을 빼고 배운다. 정답지를 못 보는 컨테이너에는 고장 구간만 넘긴다."""
    periods = subprocess.run(["python3", "eval/normal_periods.py"], check=True, capture_output=True)
    out = subprocess.run(["docker", "compose", "exec", "-T", "analysis", "python", "-m", "app.fair_anomaly"],
                         input=periods.stdout, check=True, capture_output=True)
    return json.loads(out.stdout)


def unseen(runs, rule_answers):
    """처음 보는 고장: 고장 T의 규칙이 없었다고 치면 다른 규칙이 T를 대신 알아채는가. 종류별 찾은 수를 돌려준다."""
    found = {}
    for t in {f["type"] for r in runs for f in r["faults"]}:
        without = {run: [c for c in cands if c["fault_type"] != t] for run, cands in rule_answers.items()}
        found[t] = score(runs, without, by_name=False)["found"][t]
    return found


def row(name, naming, result):
    delay = f"{statistics.median(result['all_delays']):.0f}분" if result["all_delays"] else "-"
    found = f"{result['all_found']}/{result['all_total']}"
    print(f"| {name} | {naming} | {found} ({result['all_found'] / result['all_total']:.0%}) "
          f"| {delay} | {result['all_false']} |")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev", choices=["dev", "test"])
    args = parser.parse_args()

    runs, _ = load_runs(args.split)
    rule_answers = {t["run_id"]: ask_api(t["run_id"], "rule") for t in runs}
    if args.split == "dev":
        guard_answers, guard_name = fair_guard_answers(), "경비원 (런 하나씩 빼고 배움)"
    else:
        guard_answers, guard_name = {t["run_id"]: ask_api(t["run_id"], "anomaly") for t in runs}, "경비원"

    rule = score(runs, rule_answers)
    rule_any = score(runs, rule_answers, by_name=False)
    guard = score(runs, guard_answers, by_name=False)
    hidden = unseen(runs, rule_answers)

    print(f"[{args.split}] 런 {len(runs)}개, 생산 시간 기준\n")
    print("| 방법 | 고장 이름 | 탐지 | 지연 중앙값 | 오탐 |")
    print("|---|---|---|---|---|")
    row("규칙 7개", "맞혀야 정답", rule)
    row("규칙 7개 (울렸는지만)", "안 봄", rule_any)
    row(guard_name, "모름", guard)

    print("\n| 고장 | 규칙 | 규칙 (자기 규칙 빼면) | 경비원 |")
    print("|---|---|---|---|")
    for t in sorted(guard["total"]):
        n = guard["total"][t]
        print(f"| {t} | {rule['found'][t]}/{n} | {hidden[t]}/{n} | {guard['found'][t]}/{n} |")
    print(f"| **합계** | {rule['all_found']}/{rule['all_total']} | {sum(hidden.values())}/{rule['all_total']} "
          f"| {guard['all_found']}/{guard['all_total']} |")


if __name__ == "__main__":
    main()
