#!/bin/bash
# 실시간 감시 재생 시험. 지금 코드를 analysis 이미지에 얹어 끝난 런을 다시 흘려 본다. 실제 장비와 DB는 바꾸지 않는다.
#   bash eval/explore/live_replay.sh 20261020_0800_bc0d60 [STEP분]
cd "$(dirname "$0")/../.." || exit 1
IMAGE=$(kubectl -n automachine get deploy analysis -o jsonpath='{.spec.template.spec.containers[0].image}')
set -a; source .env; set +a
for run in "$@"; do
  [ -d "logs/$run" ] || continue
  docker run --rm --network host --user "$(id -u):$(id -g)" -v "$PWD/analysis:/app" -v "$PWD/logs:/logs:ro" \
    -v "$PWD/eval/explore:/explore:ro" -w /app -e PYTHONPATH=/app -e DB_USER -e DB_PASS -e DB_NAME -e DB_HOST=127.0.0.1 -e DB_PORT=5432 \
    "$IMAGE" python /explore/live_replay.py "/logs/$run" "${STEP:-5}"
done
