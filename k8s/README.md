# k8s/

발표와 배포용 k3s 설정입니다. 개발은 계속 Docker Compose로 합니다.

```
k8s/cluster/   클러스터에 한 번만 적용 (medi-info와 공유)
k8s/app/       automachine 서비스 (네임스페이스 automachine)
k8s/deploy.sh  이미지 빌드 → 로컬 저장소에 등록 → 적용
```

## 처음 한 번

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="v1.36.5+k3s1" INSTALL_K3S_SKIP_ENABLE=true \
  INSTALL_K3S_EXEC="server --write-kubeconfig-mode 644" sh -
sudo cp k8s/cluster/registries.yaml /etc/rancher/k3s/registries.yaml
sudo systemctl start k3s
kubectl apply -f k8s/cluster/traefik-config.yaml
```

## 켜기, 배포, 끄기

WSL 메모리가 8GB라서 둘을 동시에 띄우지 않습니다. 부팅해도 k3s는 자동으로 켜지지 않습니다.

```bash
docker compose stop            # Compose 끄기 (데이터는 유지)
sudo systemctl start k3s       # k3s 켜기
bash k8s/deploy.sh             # 코드를 바꿨을 때 다시 배포
sudo k3s-killall.sh            # k3s 끄기 (systemctl stop만으로는 파드가 남음)
```

주소는 http://127.0.0.1 입니다. Windows에서 `localhost`의 IPv6 경로는 막혀 있어서, 안 열리면 `127.0.0.1`로 접속합니다.

## 데이터

k8s DB와 Compose DB는 따로입니다. 처음에 Compose DB를 복사했고, 이후 내용은 서로 반영되지 않습니다. `logs/`와 `ground_truth/`는 저장소 폴더를 그대로 씁니다.

Compose DB를 다시 복사하려면 두 DB를 모두 켠 상태에서 k8s 쪽 표를 비우고 실행합니다.

```bash
docker compose exec -T db sh -c 'pg_dump -Fc --data-only --disable-triggers -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  | kubectl -n automachine exec -i db-0 -- sh -c 'pg_restore --data-only --disable-triggers --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

## 채점

```bash
ANALYSIS_API=http://127.0.0.1/api/analysis/runs/ python3 eval/score.py --split dev
```

`eval/compare.py`의 공정 채점은 아직 Compose의 analysis 컨테이너를 씁니다.

## 왜 Traefik이 포트를 직접 여나

WSL mirrored 네트워크에서는 PC에서 Service 주소로 들어가는 경로가 시간 초과로 막힙니다 (파드에서 Service로, PC에서 파드 IP로는 됩니다). 그래서 `cluster/traefik-config.yaml`로 Traefik이 80, 443을 직접 엽니다. k3s가 켜져 있는 동안 80, 443, 8088, 9100번을 씁니다.

Ollama는 GPU를 쓰므로 클러스터 밖 WSL에서 돌고, 파드에서는 `ollama` Service를 거쳐 `10.42.0.1:11434`로 연결합니다.

## 아직 확인하지 못한 것

- 네트워크가 바뀌어 노드 IP(현재 Wi-Fi)가 달라졌을 때의 동작 (리허설 전에 확인)
- 외부 공개 (Tailscale Funnel)
