"""반장(LLM) 설명 품질 채점. 기준은 eval/README.md 8절. 사건마다 LLM이 보고서를 새로 써서 시간이 걸린다 (한 건 약 30초).

    python3 eval/score_explanations.py --split test     # 지시문을 만들 때 보지 않은 런
    python3 eval/score_explanations.py --split dev
k8s에서는 ANALYSIS_API=http://127.0.0.1/api/analysis/runs/ 를 앞에 붙인다. 결과는 scores/explanations_<split>.json.
"""
import argparse
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

from score import API, load_runs
from score_foreman import active_faults, call, right

# 정해진 원인을 확인할 때 보는 값. 목록의 정규식이 모두 근거에 나와야 한다.
SIGNALS = {
    "nozzle_clog": [r"폭|청소"],
    "temp_sensor_drift": [r"청소"],
    "vacuum_leak": [r"진공"],
    "air_supply_drop": [r"압력", r"진공"],
    "air_bubble": [r"VOID|기포|빈틈|공백|void"],
    "needle_tip_buildup": [r"STRINGING|stringing|실처럼|끌"],
    "needle_offset": [r"오프셋|offset"],
    "recipe_pressure_error": [r"설정|변경|레시피", r"압력"],
    "recipe_retract_error": [r"retract|대기 시간|DWELL|dwell"],
}
# 앞뒤에 ":"가 붙은 수는 시각("13:01:06")의 일부라 세지 않는다. 11/3 test에서 "13:01:06에서 5개"를 6 → 5로 잘못 읽었다.
NUMBER = r"(?<![\d.:])-?\d+(?:\.\d+)?(?![\d:])"
# "0.78에서 0.76", "0.78 → 0.76", 함수 결과의 "사건 전 0.78 → 사건 중 0.76"처럼 화살표 뒤에 짧은 낱말이 붙은 경우까지
PAIR = re.compile(rf"({NUMBER})\s*(?:mm|kPa|C|개|mg|%)?\s*(?:에서|→|->)\s*(?:[가-힣]+\s+){{0,2}}({NUMBER})")
DOWN = re.compile(r"감소|줄|떨어|낮아|작아|내려")
UP = re.compile(r"증가|늘|높아|커|올라")


def pairs(text):
    return [(float(a), float(b)) for a, b in PAIR.findall(text)]


def check(report, cause):
    """한 보고서의 기준별 통과 여부와 걸린 문장."""
    reasoning = report.get("reasoning", [])
    joined = "\n".join(reasoning)
    sources = {p for t in report.get("tool_results", []) for p in pairs(t)}
    reversed_, wrong_way = [], []
    for sentence in reasoning:
        for x, y in pairs(sentence):
            if (x, y) not in sources and (y, x) in sources:
                reversed_.append(f"{x} → {y}")
            if x >= 0 and y >= 0 and x != y:
                said_down, said_up = bool(DOWN.search(sentence)), bool(UP.search(sentence))
                if (y < x and said_up and not said_down) or (y > x and said_down and not said_up):
                    wrong_way.append(f"{x} → {y}")
    signal = SIGNALS.get(cause)
    result = {
        "grounded": not report.get("unverified_numbers"),
        "on_topic": not report.get("other_causes"),
        "signal": True if signal is None else all(re.search(p, joined) for p in signal),
        "order": not reversed_,
        "direction": not wrong_way,
    }
    result["good"] = all(result.values())
    result["problems"] = {"unverified": report.get("unverified_numbers", []), "other_causes": report.get("other_causes", []),
                          "reversed": reversed_, "wrong_way": wrong_way}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="test", choices=["dev", "test"])
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    rows = []
    for truth in load_runs(args.split)[0]:
        for incident in call(f"{API}{truth['run_id']}/incidents")["incidents"]:
            if args.limit and len(rows) >= args.limit:
                break
            at = incident["started_at"]
            report = call(f"{API}{truth['run_id']}/incidents/report?{urllib.parse.urlencode({'at': at})}", "POST")
            names = active_faults(truth, datetime.fromisoformat(at))
            row = {"run_id": truth["run_id"], "at": at, "cause": report["cause"],
                   "cause_right": right(report["cause"], names), "truth": sorted(names),
                   "doubts": report.get("doubts", []), "reasoning": report.get("reasoning", []),
                   **check(report, report["cause"])}
            rows.append(row)
            marks = "".join("O" if row[k] else "X" for k in ("grounded", "on_topic", "signal", "order", "direction"))
            print(f"{truth['run_id'][-6:]} {at[11:16]} {row['cause']:<22} 판단{'O' if row['cause_right'] else 'X'} "
                  f"기준 {marks} 의문 {len(row['doubts'])} {row['problems'] if not row['good'] else ''}", flush=True)

    n = len(rows)
    print(f"\n[{args.split}] 보고서 {n}개 (기준 순서: 수치 출처, 주제 일치, 핵심 단서, 순서, 방향)")
    for key, label in (("grounded", "수치 출처"), ("on_topic", "주제 일치"), ("signal", "핵심 단서"),
                       ("order", "순서 정확"), ("direction", "방향 정확"), ("good", "좋은 설명 (모두 통과)")):
        print(f"- {label}: {sum(r[key] for r in rows)}/{n}")
    wrong = [r for r in rows if not r["cause_right"]]
    rightly = [r for r in rows if r["cause_right"]]
    print(f"- 판단이 틀린 사건 {len(wrong)}개 중 의문점을 적은 보고서 {sum(bool(r['doubts']) for r in wrong)}개")
    print(f"- 판단이 맞은 사건 {len(rightly)}개 중 의문점을 적은 보고서 {sum(bool(r['doubts']) for r in rightly)}개")

    out = Path("scores") / f"explanations_{args.split}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
