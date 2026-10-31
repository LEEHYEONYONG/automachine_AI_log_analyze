#!/bin/bash
# Loads runs from logs/ into the k8s DB as a one-off Job, using the version of the analysis image now running.
#   bash k8s/ingest.sh 20261030_0800_a2eb37 [more run ids]   only these runs
#   bash k8s/ingest.sh --eval                                every run listed in eval/runs.csv
# Runs are named explicitly because logs/ also holds many live runs, one per simulator restart.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = --eval ]; then
  mapfile -t RUNS < <(python3 - <<'EOF'
import csv, json
from pathlib import Path
wanted = {(r["scenario"], r["seed"]) for r in csv.DictReader(open("eval/runs.csv", encoding="utf-8"))}
for p in sorted(Path("ground_truth").glob("*/faults.json")):
    t = json.loads(p.read_text(encoding="utf-8"))
    if (t["scenario"], str(t["seed"])) in wanted:
        print(t["run_id"])
EOF
  )
else
  RUNS=("$@")
fi
if [ ${#RUNS[@]} -eq 0 ]; then
  echo "usage: bash k8s/ingest.sh <run_id>... | --eval" >&2
  exit 2
fi

IMAGE=$(kubectl -n automachine get deploy analysis -o jsonpath='{.spec.template.spec.containers[0].image}')
NAME=ingest-$(date +%m%d%H%M%S)
ARGS=$(printf '"%s",' "${RUNS[@]}")

# Only the first "name: ingest" is the Job's; the container keeps its name.
sed -e "0,/name: ingest\$/s##name: $NAME#" -e "s#image: analysis-image#image: $IMAGE#" \
  -e "s#\"RUN_IDS\"#${ARGS%,}#" k8s/jobs/ingest.yaml | kubectl apply -f -
kubectl -n automachine wait --for=condition=complete "job/$NAME" --timeout=1800s
kubectl -n automachine logs "job/$NAME" -c ingest
