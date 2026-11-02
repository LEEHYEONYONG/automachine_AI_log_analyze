#!/bin/bash
# LLM 모델을 차례로 돌려 원인 판단을 비교한다. 분석 파드와 따로 돌아서 HPA가 파드를 줄여도 끊기지 않는다.
#   bash eval/explore/llm_compare.sh hermes3:8b qwen2.5:7b-instruct-q4_K_M
#   LIMIT=2 bash eval/explore/llm_compare.sh hermes3:8b   # 모델마다 2건만 시험
# 결과는 ~/llm_compare/<모델>.jsonl에 쌓이고, 끊겨도 다시 실행하면 이어서 돈다. 메모리 기록은 ~/llm_compare/memory.log
cd "$(dirname "$0")/../.." || exit 1
OUT=$HOME/llm_compare
mkdir -p "$OUT"
set -a; source .env; set +a

IMAGE=$(kubectl -n automachine get deploy analysis -o jsonpath='{.spec.template.spec.containers[0].image}')
( while true; do kubectl -n automachine port-forward pod/db-0 15432:5432 >/dev/null 2>&1; sleep 2; done ) &
FORWARD=$!
( while sleep 30; do echo "$(date +%H:%M:%S) $(free -m | awk 'NR==2{print "avail",$7} NR==3{print "swap",$3}' | xargs)"; done ) >> "$OUT/memory.log" &
MEMLOG=$!
trap 'kill $FORWARD $MEMLOG 2>/dev/null; pkill -f "port-forward pod/db-0 15432" 2>/dev/null' EXIT
sleep 3

in_container() {
  docker run --rm -i --network host --user "$(id -u):$(id -g)" -v "$PWD/analysis:/app" -v "$OUT:/out" \
    -e DB_USER="$DB_USER" -e DB_PASS="$DB_PASS" -e DB_NAME="$DB_NAME" -e DB_HOST=127.0.0.1 -e DB_PORT=15432 \
    -e OLLAMA_URL=http://127.0.0.1:11434 -e LIMIT="${LIMIT:-0}" "$IMAGE" "$@"
}

# 런 하나씩 빼고 배운 분류 의견은 모델 비교에서 공통이므로 한 번만 만든다.
if [ ! -s "$OUT/fair.json" ]; then
  python3 eval/normal_periods.py | in_container python -m app.train_classifier --fair > "$OUT/fair.json" || exit 1
fi

for model in "$@"; do
  echo "== $model"
  in_container python -m app.llm_compare "$model" "/out/${model%%:*}.jsonl" < "$OUT/fair.json" || echo "failed: $model"
done
