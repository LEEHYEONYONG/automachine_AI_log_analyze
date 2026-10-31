#!/bin/bash
# Builds the images, pushes them to the local registry and applies everything in k8s/app.
#   bash k8s/deploy.sh          build and deploy
#   bash k8s/deploy.sh images   only build and push
set -euo pipefail
cd "$(dirname "$0")/.."

REGISTRY=localhost:5000

# Only on this PC (127.0.0.1), and the images survive a restart in the registry-data volume.
if [ -z "$(docker ps -aq -f name=^registry$)" ]; then
  docker run -d --name registry --restart unless-stopped -p 127.0.0.1:5000:5000 \
    -v registry-data:/var/lib/registry registry:3.1.2
fi
docker start registry >/dev/null

docker build -q -t $REGISTRY/automachine-sim:dev .
docker build -q -t $REGISTRY/automachine-analysis:dev analysis
docker build -q -t $REGISTRY/automachine-web:dev -f web/Dockerfile.prod web
for name in sim analysis web; do
  docker push -q $REGISTRY/automachine-$name:dev
done
[ "${1:-}" = images ] && exit 0

kubectl apply -f k8s/app/namespace.yaml

# The password stays in .env (not in git); only names are read here, and kubectl keeps the values in the cluster.
set -a; source .env; set +a
kubectl -n automachine create secret generic db-credentials \
  --from-literal=DB_USER="$DB_USER" --from-literal=DB_PASS="$DB_PASS" --from-literal=DB_NAME="$DB_NAME" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n automachine create configmap db-init --from-file=db/init \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f k8s/app/

# The tag stays "dev", so nothing in the Deployments changed: ask for new pods to pull the new images.
kubectl -n automachine rollout restart deploy/sim deploy/analysis deploy/web
kubectl -n automachine rollout status statefulset/db --timeout=180s
for name in sim analysis web; do
  kubectl -n automachine rollout status deploy/$name --timeout=180s
done
