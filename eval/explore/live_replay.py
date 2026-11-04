"""실시간 감시 재생 시험: 끝난 런의 로그를 시뮬레이터 시간 STEP분씩 임시 폴더에 흘려 넣으며 감시 엔진을 돌린다.
경보가 처음 뜬 시점, 그때의 원인, 관련 설비 알람보다 몇 분 먼저였는지를 보고, 끝에서는 분석 버튼(DB) 결과와 비교한다.
analysis 이미지 안에서 실행한다 (eval/explore/live_replay.sh). 정답지는 읽지 않는다.

    python live_replay.py /logs/<run_id> [STEP분]
"""
import json
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from app import anomaly, classify, live

API = "http://127.0.0.1/api/analysis/runs/"


def stamped_lines(path):
    """(시각, 줄) 목록. CSV는 머리줄을 시각 None으로 두고, 시각 칸은 이름으로 찾는다."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if path.suffix != ".csv":
        return [(datetime.fromisoformat(line[:23]), line) for line in lines if len(line) > 23]
    header = lines[0].rstrip("\n").split(",")
    col = header.index("end_time" if "end_time" in header else "timestamp")
    out = [(None, lines[0])]
    for line in lines[1:]:
        value = line.split(",")[col]
        out.append((datetime.fromisoformat(value) if value else datetime.max, line))
    return out


def main():
    source = Path(sys.argv[1])
    step = timedelta(minutes=float(sys.argv[2]) if len(sys.argv) > 2 else 5)
    recipes = json.loads((source / "machine_info.json").read_text(encoding="utf-8"))["recipes"]
    files = {name: stamped_lines(source / name)
             for name in ("production.csv", "sensor_trend.csv", "event.log", "alarm.log")}
    start = min(t for lines in files.values() for t, _ in lines if t and t != datetime.max)
    end = max(t for lines in files.values() for t, _ in lines if t and t != datetime.max)
    profile, model = anomaly.load_profile(), classify.load_model()

    seen = {}   # started_at → 처음 본 시점과 그때의 원인
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / source.name
        target.mkdir()
        written = {name: 0 for name in files}
        runner = live.LiveRun(target, recipes)
        cut = start
        while cut <= end + step:
            for name, lines in files.items():
                upto = written[name]
                while upto < len(lines) and (lines[upto][0] is None or lines[upto][0] <= cut):
                    upto += 1
                with (target / name).open("a", encoding="utf-8") as f:
                    f.writelines(line for _, line in lines[written[name]:upto])
                written[name] = upto
            runner.update()
            for alert in live.analyze(runner, profile, model):
                key = alert["started_at"]
                if key not in seen:
                    seen[key] = {"seen_at": cut, "first_cause": alert["cause"]}
                seen[key]["final"] = alert
            cut += step

    with urllib.request.urlopen(f"{API}{source.name}/incidents", timeout=120) as res:
        batch = {i["started_at"]: i["cause"] for i in json.loads(res.read())["incidents"]}

    print(f"{source.name}: {start:%H:%M} ~ {end:%H:%M}, {step.total_seconds() / 60:.0f}분씩")
    print("| 사건 시작 | 화면에 뜬 시점 | 처음 원인 | 마지막 원인 | 관련 설비 알람 | 알람보다 | 분석 버튼 |")
    print("|---|---|---|---|---|---|---|")
    for key, s in sorted(seen.items()):
        a = s["final"]
        alarm = a["first_alarm"]
        lead = "-" if a["lead_min"] is None else f"{a['lead_min']:.0f}분 먼저" if a["lead_min"] >= 0 else f"{-a['lead_min']:.0f}분 늦게"
        match = "같음" if batch.get(key) == a["cause"] else f"다름({batch.get(key)})"
        print(f"| {key[11:19]} | {s['seen_at']:%H:%M} | {s['first_cause']} | {a['cause']} "
              f"| {alarm['code'] + ' ' + alarm['at'][11:16] if alarm else '없음'} | {lead} | {match} |")
    missing = sorted(set(batch) - set(seen))
    print(f"분석 버튼에만 있는 사건: {missing or '없음'}")


if __name__ == "__main__":
    main()
