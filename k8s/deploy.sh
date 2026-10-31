#!/bin/bash
# Builds the images, pushes them to the local registry and applies everything in k8s/app.
#   bash k8s/deploy.sh          build and deploy
#   bash k8s/deploy.sh images   only build and push
# Back to the previous version: kubectl -n automachine rollout undo deploy/analysis
set -euo pipefail
cd "$(dirname "$0")/.."

REGISTRY=localhost:5000

# Every version gets its own tag, which is what lets a rollback go back to it. Uncommitted code gets a unique one.
TAG=$(git rev-parse --short HEAD)
if [ -n "$(git status --porcelain)" ]; then
  TAG=$TAG-dirty-$(date +%m%d%H%M%S)
fi
echo "version: $TAG"

# Only on this PC (127.0.0.1), and the images survive a restart in the registry-data volume.
if [ -z "$(docker ps -aq -f name=^registry$)" ]; then
  docker run -d --name registry --restart unless-stopped -p 127.0.0.1:5000:5000 \
    -v registry-data:/var/lib/registry registry:3.1.2
fi
docker start registry >/dev/null

docker build -q -t $REGISTRY/automachine-sim:$TAG .
docker build -q -t $REGISTRY/automachine-analysis:$TAG analysis
docker build -q -t $REGISTRY/automachine-web:$TAG -f web/Dockerfile.prod web
for name in sim analysis web; do
  docker push -q $REGISTRY/automachine-$name:$TAG
done
[ "${1:-}" = images ] && exit 0

kubectl apply -f k8s/app/namespace.yaml

# The password stays in .env (not in git); kubectl keeps the values in the cluster.
set -a; source .env; set +a
kubectl -n automachine create secret generic db-credentials \
  --from-literal=DB_USER="$DB_USER" --from-literal=DB_PASS="$DB_PASS" --from-literal=DB_NAME="$DB_NAME" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n automachine create configmap db-init --from-file=db/init \
  --dry-run=client -o yaml | kubectl apply -f -

# The files say :dev; each deployment fills in its own version, and the changed tag starts the rolling update.
for f in k8s/app/*.yaml; do
  sed "s#\(localhost:5000/automachine-[a-z]*\):dev#\1:$TAG#" "$f" | kubectl apply -f -
done
kubectl -n automachine annotate deploy sim analysis web kubernetes.io/change-cause="$TAG" --overwrite

kubectl -n automachine rollout status statefulset/db --timeout=180s
for name in sim analysis web; do
  kubectl -n automachine rollout status deploy/$name --timeout=180s
done
