#!/bin/bash
# 실험 ②: 교대 인수인계 요약 (analysis/app/handover.py). 저장소 맨 위에서 실행한다.
#   bash eval/explore/handover.sh              # dev 런의 교대마다 쓰고 검사한다
#   SPLIT=test bash eval/explore/handover.sh   # test: dev에서 지시문을 다 정한 뒤 한 번만
# 결과는 ~/llm_compare/handover_summary_<split>.jsonl. 끊겨도 다시 실행하면 이어서 돈다. medi-info를 끄고 돌린다.
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

SPLIT=$SPLIT python3 -c '
import json, os, sys
sys.path.insert(0, "eval")
from score import load_runs
print(json.dumps([t["run_id"] for t in load_runs(os.environ["SPLIT"])[0]]))' > "$OUT/handover_input_$SPLIT.json" || exit 1

docker run --rm -i --network host --user "$(id -u):$(id -g)" -v "$PWD/analysis:/app" -v "$OUT:/out" \
  -e DB_USER="$DB_USER" -e DB_PASS="$DB_PASS" -e DB_NAME="$DB_NAME" -e DB_HOST=127.0.0.1 -e DB_PORT=15432 \
  -e OLLAMA_URL=http://127.0.0.1:11434 \
  "$IMAGE" python -m app.handover "/out/handover_summary_$SPLIT.jsonl" < "$OUT/handover_input_$SPLIT.json"
