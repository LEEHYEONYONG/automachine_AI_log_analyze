"""LLM 모델 비교 채점. 기준은 eval/README.md 7절과 같다 (dev 런만). 저장소 맨 위에서 실행한다.

    python3 eval/explore/llm_compare_score.py ~/llm_compare/*.jsonl
"""
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "eval")
from score import load_runs            # noqa: E402
from score_foreman import active_faults, right   # noqa: E402

SPLIT = "test" if any(name.endswith(".test.jsonl") for name in sys.argv[1:]) else "dev"
truths = {t["run_id"]: t for t in load_runs(SPLIT)[0]}
print(f"[{SPLIT}]")
results = {}
for name in sys.argv[1:]:
    rows = {}
    for line in Path(name).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["run_id"] in truths:    # 다른 split의 런이 섞이면 뺀다
            rows[(row["run_id"], row["at"])] = row
    results[Path(name).stem] = rows

keys = sorted({k for rows in results.values() for k in rows})
print("| 런 | 시각 | 정답 | 규칙 | " + " | ".join(results) + " |")
print("|---|---|---|---|" + "---|" * len(results))
for run_id, at in keys:
    names = active_faults(truths[run_id], datetime.fromisoformat(at))
    first = next(r[(run_id, at)] for r in results.values() if (run_id, at) in r)
    cells = []
    for rows in results.values():
        row = rows.get((run_id, at))
        cause = "-" if row is None else row.get("cause", "오류")
        cells.append(("O " if row and right(row.get("cause"), names) else "X ") + cause)
    rule = first["rule"]
    print(f"| {run_id[-6:]} | {at[11:16]} | {', '.join(sorted(names)) or '없음'} "
          f"| {'O' if right(rule, names) else 'X'} {rule or '-'} | " + " | ".join(cells) + " |")

for model, rows in results.items():
    good = [r for r in rows.values() if "error" not in r]
    errors = len(rows) - len(good)
    hit = rule_hit = fixed = broke = wrong_high = 0
    for r in good:
        names = active_faults(truths[r["run_id"]], datetime.fromisoformat(r["at"]))
        ok, rule_ok = right(r["cause"], names), right(r["rule"], names)
        hit += ok
        rule_hit += rule_ok
        fixed += ok and not rule_ok
        broke += rule_ok and not ok
        wrong_high += (not ok) and r["confidence"] == "high"
    seconds = sorted(r["seconds"] for r in good)
    print(f"\n## {model}: 사건 {len(good)}개 (오류 {errors})")
    print(f"- 원인 정답 {hit}/{len(good)}, 같은 사건에서 규칙 {rule_hit}/{len(good)}")
    print(f"- 규칙이 틀린 것을 바로잡음 {fixed}건, 규칙이 맞힌 것을 망침 {broke}건")
    print(f"- 틀린 답 중 확신 high {wrong_high}건, 출처 없는 수치가 있는 답 {sum(bool(r['unverified_numbers']) for r in good)}건")
    print(f"- 함수를 스스로 하나라도 부른 답 {sum(bool(r['called_by_model']) for r in good)}건, 판단 불가 {sum(r['cause'] == 'unknown' for r in good)}건")
    if seconds:
        print(f"- 사건당 시간 중앙값 {seconds[len(seconds) // 2]}초, 최대 {seconds[-1]}초")
    print(f"- 고른 이름: {dict(Counter(r['cause'] for r in good).most_common())}")
    if any("cost_usd" in r for r in good):
        print(f"- 계산 비용 ${sum(r.get('cost_usd', 0) for r in good):.2f} (실제 청구는 Console 기준), "
              f"실제 답한 모델 {dict(Counter(m for r in good for m in r.get('served_by', [])))}")
