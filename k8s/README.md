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

## 버전과 되돌리기

배포할 때마다 이미지에 커밋 번호로 태그를 붙입니다. 커밋 전 코드는 `커밋번호-dirty-시각`이 됩니다. 커밋이 같으면 태그도 같아서 파드를 바꾸지 않습니다.

analysis와 web은 새 파드가 준비된 뒤에 옛 파드를 내립니다. 그래서 새 버전이 뜨지 못해도 옛 파드가 계속 응답합니다. sim은 둘이 동시에 돌면 안 되므로 옛 파드를 먼저 내리고, 그동안 끊기며 돌던 장비 상태는 사라집니다.

```bash
kubectl -n automachine rollout history deploy/analysis   # 지난 버전 보기
kubectl -n automachine rollout undo deploy/analysis      # 직전 버전으로 되돌리기
```

되돌린 뒤 `deploy.sh`를 다시 실행하면 지금 코드로 배포됩니다.

## 로그 적재

`logs/`에는 시뮬레이터가 재시작할 때마다 생기는 라이브 런도 많아서, 적재할 런을 직접 지정합니다. 같은 런을 다시 적재하면 그 런의 기존 행을 지우고 새로 넣습니다.

```bash
bash k8s/ingest.sh 20261031_0800_7714b3   # 지정한 런
bash k8s/ingest.sh --eval                 # eval/runs.csv의 33런
```

Job이 실패하면 `ingest.sh`는 최대 30분까지 기다린 뒤에 끝납니다. 오래 걸리면 `kubectl -n automachine get pods`로 확인합니다.

## 상태 점검과 자원

| 서비스 | 살아 있나 (실패하면 재시작) | 요청을 받아도 되나 (실패하면 트래픽 제외) | 메모리 제한 | 측정한 최대치 |
|---|---|---|---|---|
| db | `pg_isready` | `pg_isready` | 1536Mi | 약 280MB (복사 직후 853MB) |
| sim | `/api/state` | `/api/state` | 512Mi | 약 60MB |
| analysis | `/api/analysis/live` | `/api/analysis/ready` (DB 확인) | 1Gi | 약 100MB |
| web | `/` | `/` | 64Mi | 약 13MB |

analysis의 살아 있나 점검은 일부러 DB를 보지 않습니다. DB가 죽었을 때 앱을 재시작해도 소용없기 때문입니다. GPU는 k8s가 관리하지 않습니다 (Ollama가 클러스터 밖에 있음).

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

## 운영 화면

http://127.0.0.1/#ops 에서 노드, GPU, LLM 상태와 서비스 상태판, 배포 현황, 이벤트, 로그를 봅니다. "파드 죽이기"를 누르면 복구 과정이 기록됩니다.

```bash
# 파드 죽이기에 필요한 운영 토큰 보기
kubectl -n automachine get secret ops-token -o jsonpath='{.data.token}' | base64 -d; echo
```

- 이 PC 안에서만 열립니다. 다른 주소로 들어오면 Traefik이 403을 돌려주고, Tailscale Funnel 요청은 ops가 거절합니다.
- 죽일 수 있는 건 web과 analysis뿐입니다. db는 전체가 멈추고, sim은 돌던 장비 상태가 사라지기 때문입니다.
- ops 계정(`k8s/app/ops.yaml`)은 Secret을 읽거나 Deployment를 바꿀 수 없고, 파드 삭제만 쓰기 권한입니다.
- GPU 수집기(`gpu-metrics`)는 WSL 제약으로 특권 파드입니다. 그래서 ops와 분리했고 k8s 계정을 주지 않았습니다.
- 메모리 값은 k8s 측정값이라 캐시 일부가 포함되어, `free`의 used보다 크게 나옵니다. Windows 전체 메모리는 보이지 않습니다.

## DB 백업

`db-backup` CronJob이 매일 12:30(KST)에 `backups/db_날짜_시각.dump`를 만들고 최근 3개만 남깁니다. k3s가 꺼져 있어 놓쳐도 6시간 안에 켜면 실행됩니다. 결과는 운영 화면의 "저장 공간과 백업"에서 봅니다.

```bash
# 지금 바로 백업
kubectl -n automachine create job --from=cronjob/db-backup backup-$(date +%m%d%H%M)

# 복원 (현재 DB 내용을 덮어씁니다)
kubectl -n automachine exec -i db-0 -- sh -c 'pg_restore --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backups/파일이름.dump
```

- 백업은 이 PC의 WSL 디스크에만 있습니다. 디스크 고장이나 PC 교체에 대비하려면 다른 곳에 복사해야 합니다.
- 운영 화면은 표 내용을 읽을 수 없는 `ops_reader` 계정으로 DB 크기와 연결 수만 봅니다.

## 왜 Traefik이 포트를 직접 여나

WSL mirrored 네트워크에서는 PC에서 Service 주소로 들어가는 경로가 시간 초과로 막힙니다 (파드에서 Service로, PC에서 파드 IP로는 됩니다). 그래서 `cluster/traefik-config.yaml`로 Traefik이 80, 443을 직접 엽니다. k3s가 켜져 있는 동안 80, 443, 8088, 9100번을 씁니다.

Ollama는 GPU를 쓰므로 클러스터 밖 WSL에서 돌고, 파드에서는 `ollama` Service를 거쳐 `10.42.0.1:11434`로 연결합니다.

## 아직 확인하지 못한 것

- 네트워크가 바뀌어 노드 IP(현재 Wi-Fi)가 달라졌을 때의 동작 (리허설 전에 확인)
- 외부 공개 (Tailscale Funnel)
