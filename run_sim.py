"""Run one scenario of the virtual dispensing cell.

    python run_sim.py config/scenarios/nozzle_clog.json
    python run_sim.py config/scenarios/normal.json --hours 1 --seed 7
"""
import argparse
import json
import time
from pathlib import Path

from simulator.simulation import Simulation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the virtual dispensing cell and write logs.")
    parser.add_argument("scenario", type=Path, help="scenario JSON file")
    parser.add_argument("--machine", type=Path, default=Path("config/machine.json"))
    parser.add_argument("--hours", type=float, help="override the scenario duration")
    parser.add_argument("--seed", type=int, help="override the scenario seed")
    parser.add_argument("--out", type=Path, default=Path("."), help="folder that receives logs/ and ground_truth/")
    args = parser.parse_args()

    machine_cfg = json.loads(args.machine.read_text(encoding="utf-8"))
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))

    started = time.perf_counter()
    summary = Simulation(machine_cfg, scenario, args.out, seed=args.seed).run(args.hours)
    summary["wall_time_s"] = round(time.perf_counter() - started, 1)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
