"""매일 자동 채점의 1단계: 그날의 새 런을 만든다. k8s CronJob(auto-eval)이 시뮬레이터 이미지에서 실행한다.
시나리오 11개 중 하루 3개를 돌아가며 고르고, 시드는 날짜로 정한다. 그래서 dev/test와 겹치지 않고 다시 실행해도 같은 런이다.
이미 만든 런은 건너뛰고, 그날의 run_id 목록을 파일로 남긴다 (2·3단계가 읽음).

    python eval/auto_runs.py /work/run_ids            # 오늘(한국 시각)
    python eval/auto_runs.py /work/run_ids 2026-11-03 # 날짜 지정
"""
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PER_DAY = 3
KST = timezone(timedelta(hours=9))     # 이미지에 시간대 자료가 없어 고정 오프셋을 쓴다
SCENARIOS = sorted(p.stem for p in Path("config/scenarios").glob("*.json"))


def plan(day):
    """그날의 (시나리오, 시드). 날마다 3칸씩 밀려서 약 4일이면 시나리오 11개를 한 바퀴 돈다."""
    start = day.toordinal() * PER_DAY
    return [(SCENARIOS[(start + i) % len(SCENARIOS)], int(f"{day:%Y%m%d}") * 10 + i) for i in range(PER_DAY)]


def existing():
    """ground_truth에 이미 있는 런: (시나리오, 시드) → run_id"""
    found = {}
    for path in Path("ground_truth").glob("*/faults.json"):
        truth = json.loads(path.read_text(encoding="utf-8"))
        found[(truth["scenario"], int(truth["seed"]))] = truth["run_id"]
    return found


def main():
    out = Path(sys.argv[1])
    day = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime.now(KST).date()
    run_ids = []
    for scenario, seed in plan(day):
        done = existing().get((scenario, seed))
        if done:
            print(f"{scenario} seed {seed}: 이미 있음 {done}", flush=True)
            run_ids.append(done)
            continue
        subprocess.run([sys.executable, "run_sim.py", f"config/scenarios/{scenario}.json", "--seed", str(seed),
                        "--out", "."], check=True, capture_output=True)
        run_id = existing()[(scenario, seed)]
        print(f"{scenario} seed {seed}: 만듦 {run_id}", flush=True)
        run_ids.append(run_id)
    out.write_text("\n".join(run_ids) + "\n", encoding="utf-8")
    Path(out.parent / "day").write_text(day.isoformat(), encoding="utf-8")


if __name__ == "__main__":
    main()
