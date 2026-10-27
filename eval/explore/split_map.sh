#!/bin/bash
# Map eval/runs.csv rows (scenario, seed, split) to run_id via ground_truth faults.json.
cd "$(dirname "$0")/../.." || exit 1
python3 - <<'EOF'
import csv, json, glob, os
idx = {}
for p in glob.glob("ground_truth/*/faults.json"):
    t = json.load(open(p, encoding="utf-8"))
    idx[(t["scenario"], str(t["seed"]))] = os.path.basename(os.path.dirname(p))
for row in csv.DictReader(open("eval/runs.csv", encoding="utf-8")):
    print(row["split"], row["scenario"], row["seed"], idx.get((row["scenario"], row["seed"]), "?"), sep="\t")
EOF
