"""실험 ① 채점 (analysis/app/unseen_llm.py의 결과). 저장소 맨 위에서 실행한다.

    python3 eval/explore/unseen_llm_score.py ~/llm_compare/unseen_dev.jsonl

A: 숨긴 고장 T의 이름을 맞혀야 정답. 같은 사건에서 결정 트리(T를 배운 트리)와 비교한다.
B: 목록에 T가 없으므로 other를 고르고, 부품과 문제가 아래 짝과 같아야 정답. 부품만 맞은 것은 따로 센다.
   트리는 T라는 이름을 모르므로 B에서는 0이다.
대조군(진행 중인 고장 없음): 둘 다 no_fault라고 해야 맞다.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# 고장 → (부품, 문제). 부품 설명서의 진단표와 같은 짝이다.
EXPECTED = {
    "nozzle_clog": ("니들", "막힘"),
    "needle_tip_buildup": ("니들", "끝 오염"),
    "needle_offset": ("니들", "위치 어긋남"),
    "vacuum_leak": ("진공 고정 지그", "누설·마모"),
    "air_supply_drop": ("공압 조합 유닛", "공급 압력 저하"),
    "temp_sensor_drift": ("시린지 히터", "센서 치우침"),
    "air_bubble": ("시린지", "기포"),
    "recipe_pressure_error": ("디스펜서 컨트롤러", "설정값 변경"),
    "recipe_retract_error": ("디스펜서 컨트롤러", "설정값 변경"),
}


def verdict(row):
    """(정답, 부품만 맞음)"""
    hidden = row["hidden"]
    if hidden is None:
        return row["cause"] == "no_fault", False
    if row["condition"] == "A":
        return row["cause"] == hidden, False
    want = EXPECTED[hidden]
    if row["cause"] != "other":
        return False, False
    return (row["component"], row["problem"]) == want, row["component"] == want[0]


def main():
    rows = {}
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        rows[(row["condition"], row["run_id"], row["at"], row["hidden"])] = row     # 다시 돌린 것은 마지막 줄

    keys = sorted({k[1:] for k in rows}, key=lambda k: (k[2] or "~", k[0], k[1]))
    print("| 런 | 시각 | 숨긴 고장 | 트리 | A | B (부품 / 문제) |\n|---|---|---|---|---|---|")
    for run_id, at, hidden in keys:
        a, b = rows.get(("A", run_id, at, hidden)), rows.get(("B", run_id, at, hidden))
        tree = (a or b)["tree"]

        def cell(r):
            if r is None:
                return "-"
            if "error" in r:
                return "오류"
            ok, part = verdict(r)
            mark = "O" if ok else ("△" if part else "X")
            extra = f" ({r['component']} / {r['problem']})" if r["condition"] == "B" and r["cause"] == "other" else ""
            return f"{mark} {r['cause']}{extra}"
        tree_mark = "O" if hidden and tree == hidden else "X"
        print(f"| {run_id[-6:]} | {at[11:16]} | {hidden or '대조군'} | {tree_mark} {tree or '-'} | {cell(a)} | {cell(b)} |")

    for condition in ("A", "B"):
        good = [r for k, r in rows.items() if k[0] == condition and "error" not in r]
        if not good:
            continue
        errors = sum(1 for k, r in rows.items() if k[0] == condition and "error" in r)
        faults = [r for r in good if r["hidden"]]
        hits = sum(verdict(r)[0] for r in faults)
        parts = sum(verdict(r)[1] for r in faults)
        tree = sum(r["tree"] == r["hidden"] for r in faults)
        by_type = defaultdict(lambda: [0, 0])
        for r in faults:
            by_type[r["hidden"]][0] += verdict(r)[0]
            by_type[r["hidden"]][1] += 1
        wrong_high = sum(1 for r in faults if not verdict(r)[0] and r["confidence"] == "high")
        seconds = sorted(r["seconds"] for r in good)
        print(f"\n## 조건 {condition}: 사건 {len(good)}개 (오류 {errors})")
        print(f"- 숨긴 고장의 이름 정답 {hits}/{len(faults)}"
              + (f", 같은 사건에서 트리 {tree}/{len(faults)}" if condition == "A" else ", 트리는 이름을 몰라 0")
              + (f", 부품만 맞음 {parts}건" if condition == "B" else ""))
        print("- 고장별: " + ", ".join(f"{t} {h}/{n}" for t, (h, n) in sorted(by_type.items())))
        controls = [r for r in good if not r["hidden"]]
        if controls:
            print(f"- 대조군(고장 없음) no_fault {sum(verdict(r)[0] for r in controls)}/{len(controls)}")
        print(f"- 틀린 답 중 확신 high {wrong_high}건, 출처 없는 수치가 있는 답 {sum(bool(r['unverified_numbers']) for r in good)}건, "
              f"판단 불가 {sum(r['cause'] == 'unknown' for r in good)}건")
        print(f"- 함수를 스스로 하나라도 부른 답 {sum(bool(r['called_by_model']) for r in good)}건, "
              f"설명서를 찾은 답 {sum(bool(r['manual_sections']) for r in good)}건")
        print(f"- 고른 이름: {dict(Counter(r['cause'] for r in good).most_common())}")
        if condition == "B":
            print(f"- other일 때 고른 (부품, 문제): "
                  f"{dict(Counter((r['component'], r['problem']) for r in good if r['cause'] == 'other').most_common())}")
        print(f"- 사건당 시간 중앙값 {seconds[len(seconds) // 2]}초, 최대 {seconds[-1]}초")


if __name__ == "__main__":
    main()
