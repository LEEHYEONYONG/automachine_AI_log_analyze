"""매일 자동 채점의 3단계: 그날 만든 런을 분석 API로 분석하고 정답지와 비교해 scores/에 남긴다.
채점 기준은 eval/README.md와 같다. LLM은 GPU를 오래 쓰므로 부르지 않는다 (원인은 코드가 정하므로 점수에는 영향 없음).

    ANALYSIS_API=http://analysis:8000/api/analysis/runs/ python eval/auto_score.py /work/run_ids scores/
"""
import json
import statistics
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from score import API, ask_api, score
from score_foreman import active_faults, right


def incidents(run_id):
    with urllib.request.urlopen(f"{API}{run_id}/incidents", timeout=300) as res:
        return json.loads(res.read())["incidents"]


def detection(result):
    delays = result["all_delays"]
    return {"found": result["all_found"], "total": result["all_total"], "false_alarms": result["all_false"],
            "delay_median_min": round(statistics.median(delays), 1) if delays else None,
            "missed": {t: result["total"][t] - result["found"][t] for t in result["total"] if result["found"][t] < result["total"][t]}}


def main():
    run_ids = Path(sys.argv[1]).read_text(encoding="utf-8").split()
    out_dir = Path(sys.argv[2])
    day = (Path(sys.argv[1]).parent / "day").read_text(encoding="utf-8").strip()
    truths = [json.loads((Path("ground_truth") / r / "faults.json").read_text(encoding="utf-8")) for r in run_ids]

    answers = {m: {t["run_id"]: ask_api(t["run_id"], m) for t in truths} for m in ("rule", "anomaly", "classify")}
    report = {
        "day": day,
        "scored_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "runs": [{"run_id": t["run_id"], "scenario": t["scenario"], "seed": t["seed"],
                  "faults": [f["type"] for f in t["faults"]]} for t in truths],
        "detection": {
            "rule": detection(score(truths, answers["rule"])),
            "anomaly": detection(score(truths, answers["anomaly"], by_name=False)),
            "classify": detection(score(truths, answers["classify"])),
        },
    }

    hits = {"rule_first": 0, "decision": 0}
    rows = []
    for t in truths:
        for incident in incidents(t["run_id"]):
            names = active_faults(t, datetime.fromisoformat(incident["started_at"]))
            rule_name = incident["rule_names"][0] if incident["rule_names"] else None
            hits["rule_first"] += right(rule_name, names)
            hits["decision"] += right(incident["cause"], names)
            rows.append({"run_id": t["run_id"], "at": incident["started_at"], "truth": sorted(names),
                         "rule": rule_name, "decision": incident["cause"], "basis": incident["basis"]})
    report["cause"] = {"incidents": len(rows), **hits, "rows": rows}

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"auto_{day.replace('-', '')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    d = report["detection"]
    print(f"{day} 런 {len(truths)}개: " + ", ".join(f"{r['scenario']}" for r in report["runs"]))
    for name, label in (("rule", "규칙"), ("anomaly", "경비원"), ("classify", "경비원+분류")):
        print(f"  탐지 {label}: {d[name]['found']}/{d[name]['total']}, 오탐 {d[name]['false_alarms']}, "
              f"지연 중앙값 {d[name]['delay_median_min']}분")
    print(f"  사건 {len(rows)}개 원인: 규칙의 첫 이름 {hits['rule_first']}, 코드 판단 {hits['decision']}")
    print(f"  저장: {path}")


if __name__ == "__main__":
    main()
