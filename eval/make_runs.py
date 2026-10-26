import csv
from pathlib import Path
import subprocess
import json

RUNS_FILE = Path("eval/runs.csv")

done = set()
for path in Path("ground_truth").glob("*/faults.json"):
    truth = json.loads(path.read_text(encoding="utf-8"))
    done.add((truth["scenario"], str(truth["seed"])))


with RUNS_FILE.open(encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if (row["scenario"], row["seed"]) in done:
            print("skip", row["scenario"], row["seed"])
            continue

        cmd = ["python", "run_sim.py",
               f"config/scenarios/{row['scenario']}.json",
               "--seed", row["seed"]]
        if row["hours"]:
            cmd += ["--hours", row["hours"]]
        print(" ".join(cmd))
        subprocess.run(cmd,check=True)