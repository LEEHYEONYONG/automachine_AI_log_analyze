#!/bin/bash
# 실험 ①: 규칙이 없는 고장에 LLM이 이름을 붙이는가 (analysis/app/unseen_llm.py). 저장소 맨 위에서 실행한다.
#   DRY=1 bash eval/explore/unseen_llm.sh          # LLM 없이 고를 사건만 센다
#   bash eval/explore/unseen_llm.sh                 # dev, 조건 A와 B
#   SPLIT=test bash eval/explore/unseen_llm.sh      # test: dev에서 지시문을 다 정한 뒤 한 번만
# 결과는 ~/llm_compare/unseen_<split>.jsonl에 쌓이고, 끊겨도 다시 실행하면 이어서 돈다. medi-info를 끄고 돌린다.
cd "$(dirname "$0")/../.." || exit 1
docker ps --format '{{.Names}}' | grep -q medi-info && { echo "medi-info가 켜져 있습니다. 끄고 다시 실행하세요"; exit 1; }
OUT=$HOME/llm_compare
SPLIT=${SPLIT:-dev}
mkdir -p "$OUT"
set -a; source .env; set +a

IMAGE=$(kubectl -n automachine get deploy analysis -o jsonpath='{.spec.template.spec.containers[0].image}')
( while true; do kubectl -n automachine port-forward pod/db-0 15432:5432 >/dev/null 2>&1; sleep 2; done ) &
FORWARD=$!
( while sleep 30; do echo "$(date +%H:%M:%S) $(free -m | awk 'NR==2{print "avail",$7} NR==3{print "swap",$3}' | xargs)"; done ) >> "$OUT/memory.log" &
MEMLOG=$!
trap 'kill $FORWARD $MEMLOG 2>/dev/null; pkill -f "port-forward pod/db-0 15432" 2>/dev/null' EXIT
sleep 3

# 고장 구간: 사건을 고를 때만 쓴다. dev는 그 런을 빼고 배운 트리 의견(~/llm_compare/fair.json)을 함께 넘긴다.
INPUT=$OUT/unseen_input_$SPLIT.json
SPLIT=$SPLIT FAIR=$OUT/fair.json python3 - > "$INPUT" <<'EOF' || exit 1
import json, os, sys
sys.path.insert(0, "eval")
from score import load_runs
runs, _ = load_runs(os.environ["SPLIT"])
periods = {t["run_id"]: [{"type": f["type"], "start": f["injected_at"],
                          "end": f.get("resolved_at") or "9999-12-31T00:00:00"} for f in t["faults"]] for t in runs}
fair = {}
if os.environ["SPLIT"] == "dev":
    fair = json.load(open(os.environ["FAIR"]))
    fair = {r: fair[r] for r in periods if r in fair}
json.dump({"periods": periods, "fair": fair}, sys.stdout)
EOF

docker run --rm -i --network host --user "$(id -u):$(id -g)" -v "$PWD/analysis:/app" -v "$OUT:/out" \
  -e DB_USER="$DB_USER" -e DB_PASS="$DB_PASS" -e DB_NAME="$DB_NAME" -e DB_HOST=127.0.0.1 -e DB_PORT=15432 \
  -e OLLAMA_URL=http://127.0.0.1:11434 -e DRY="${DRY:-0}" -e CONDITIONS="${CONDITIONS:-A,B}" \
  "$IMAGE" python -m app.unseen_llm "/out/unseen_$SPLIT.jsonl" < "$INPUT"
