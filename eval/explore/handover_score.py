"""실험 ② 채점: 교대 인수인계의 LLM 요약 (analysis/app/handover.py). 저장소 맨 위에서 실행한다.

    python3 eval/explore/handover_score.py ~/llm_compare/handover_summary_dev.jsonl [번호 ...]

전체 기록 목록은 코드가 붙이므로 빠짐이 없다. 채점하는 것은 맨 위 요약이다.
- 꼭 담을 것: 이어 볼 일(교대 끝까지 이어진 AI 경보), 그다음 최근 AI 경보 2개. AI 경보가 없으면 가장 잦은 알람.
- 지어냄: 사실에 없는 수치, 알람 코드, 시각.
- 이어 볼 일을 첫 문장에 썼는지, 요약 3문장·할 일 2문장을 넘지 않았는지.
번호를 주면 그 교대의 요약 전문을 보여 준다.
"""
import json
import sys
from pathlib import Path

rows = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
good = [r for r in rows if "error" not in r]
must = sum(len(r["must"]) for r in good)
missing = sum(len(r["missing"]) for r in good)
made_up = [r for r in good if r["made_up_numbers"] or r["made_up_codes"] or r["made_up_times"]]
opened = [r for r in good if r["has_open"]]
seconds = sorted(r["seconds"] for r in good)

print(f"교대 {len(rows)}개 (오류 {len(rows) - len(good)})")
print(f"- 꼭 담을 것 {must - missing}/{must}, 다 담은 요약 {sum(not r['missing'] for r in good)}/{len(good)}")
print(f"- 지어낸 것이 있는 요약 {len(made_up)}/{len(good)} (수치 {sum(len(r['made_up_numbers']) for r in good)}, "
      f"코드 {sum(len(r['made_up_codes']) for r in good)}, 시각 {sum(len(r['made_up_times']) for r in good)})")
print(f"- 이어 볼 일이 있는 교대 {len(opened)}개 중 첫 문장에 쓴 요약 {sum(r['open_first'] for r in opened)}")
print(f"- 줄 수를 넘긴 요약 {sum(r['too_long'] for r in good)}, 요약 길이 중앙값 "
      f"{sorted(len(' '.join(r['summary'] + r['todo'])) for r in good)[len(good) // 2]}자")
print(f"- 시간 중앙값 {seconds[len(seconds) // 2]}초, 최대 {seconds[-1]}초")
print("\n문제가 있는 교대:")
for i, r in enumerate(rows):
    if "error" in r:
        print(f"{i} {r['run_id'][-6:]} 오류 {r['error']}")
    elif r["missing"] or r in made_up or (r["has_open"] and not r["open_first"]) or r["too_long"]:
        print(f"{i} {r['run_id'][-6:]} {r['shift'][5:13]} 빠짐 {r['missing']} 지어냄 "
              f"{r['made_up_numbers'] + r['made_up_codes'] + r['made_up_times']} 이어볼일앞 {r['open_first']} 김 {r['too_long']}")
for i in (int(a) for a in sys.argv[2:]):
    r = rows[i]
    print(f"\n=== {i} {r['run_id']} {r['shift']}\n꼭 담을 것: {r['must']}\n{r['handover']}")
