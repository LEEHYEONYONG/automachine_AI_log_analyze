#!/bin/bash
# LLM 모델을 차례로 돌려 원인 판단을 비교한다. 분석 파드와 따로 돌아서 HPA가 파드를 줄여도 끊기지 않는다.
#   bash eval/explore/llm_compare.sh hermes3:8b qwen2.5:7b-instruct-q4_K_M
#   LIMIT=2 bash eval/explore/llm_compare.sh hermes3:8b   # 모델마다 2건만 시험
# 결과는 ~/llm_compare/<모델>.jsonl에 쌓이고, 끊겨도 다시 실행하면 이어서 돈다. 메모리 기록은 ~/llm_compare/memory.log
# claude-로 시작하는 모델은 ~/llm_compare/anthropic.env의 키를 쓰고, MAX_USD(기본 8달러)를 넘으면 멈춘다.
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
    -e OLLAMA_URL=http://127.0.0.1:11434 -e LIMIT="${LIMIT:-0}" -e MAX_USD="${MAX_USD:-8}" \
    ${ENV_FILE:+--env-file "$ENV_FILE"} "$IMAGE" "$@"
}

# 런 하나씩 빼고 배운 분류 의견은 모델 비교에서 공통이므로 한 번만 만든다.
# SPLIT=test면 dev로 배운 분류 모델의 의견을 쓰고, 결과 파일 이름에 .test가 붙는다.
SUFFIX=
INPUT=$OUT/fair.json
if [ "${SPLIT:-dev}" = test ]; then
  SUFFIX=.test
  INPUT=$OUT/test_input.json
  if [ ! -s "$INPUT" ]; then
    ANALYSIS_API=http://127.0.0.1/api/analysis/runs/ python3 eval/explore/llm_compare_test_input.py > "$INPUT" || exit 1
  fi
elif [ ! -s "$INPUT" ]; then
  python3 eval/normal_periods.py | in_container python -m app.train_classifier --fair > "$INPUT" || exit 1
fi

for model in "$@"; do
  echo "== $model"
  if [[ $model == claude-* ]]; then
    # 키는 이 실행에만 넘기고, SDK도 제품 이미지에 넣지 않는다.
    ENV_FILE=$OUT/anthropic.env in_container sh -c \
      'pip install -q --no-cache-dir --target /tmp/pkgs anthropic==2.3.0 && PYTHONPATH=/tmp/pkgs python -m app.llm_compare "$0" "$1"' \
      "$model" "/out/$model$SUFFIX.jsonl" < "$INPUT" || echo "failed: $model"
  else
    in_container python -m app.llm_compare "$model" "/out/${model%%:*}$SUFFIX.jsonl" < "$INPUT" || echo "failed: $model"
  fi
done
