# k8s/

발표와 배포용 k3s 설정입니다. 개발은 계속 Docker Compose로 합니다.

```
k8s/cluster/    클러스터에 한 번만 적용 (medi-info와 공유)
k8s/app/        automachine 서비스의 공통 설정 (네임스페이스 automachine)
k8s/overlays/   환경별 차이: dev(개발), demo(발표)
k8s/deploy.sh   이미지 빌드 → 로컬 저장소에 등록 → 한 환경 적용
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
bash k8s/deploy.sh             # 코드를 바꿨을 때 다시 배포 (개발용 설정)
sudo k3s-killall.sh            # k3s 끄기 (systemctl stop만으로는 파드가 남음)
```

주소는 http://127.0.0.1 입니다. Windows에서 `localhost`의 IPv6 경로는 막혀 있어서, 안 열리면 `127.0.0.1`로 접속합니다.

## 개발용과 발표용 설정 (Kustomize)

`k8s/app/`이 공통 설정이고, `k8s/overlays/<환경>/`이 그 위에 덮는 차이입니다. `deploy.sh`가 둘을 합쳐 적용합니다.

```bash
bash k8s/deploy.sh demo        # 발표 전에
bash k8s/deploy.sh dev         # 발표 뒤에 (인자 없이 실행해도 dev)
kubectl kustomize k8s/overlays/demo   # 실제로 적용될 설정을 미리 보기
```

| | dev | demo | 이유 |
|---|---|---|---|
| 웹 화면 파드 | 1개 | 2개 | 발표 중 파드를 죽여도 화면이 끊기지 않게 |
| AI 분석 최소 파드 (HPA) | 1개 | 2개 | 같은 이유. 부하가 오면 둘 다 3개까지 늘어남 |
| 매일 자동 채점 | 켜짐 | 일시 정지 | 21:00 채점(또는 k3s를 켤 때의 따라잡기)이 발표 중에 CPU와 DB를 쓰지 않게 |

- 모든 리소스에 `automachine/env` 라벨이 붙어 지금 환경을 알 수 있습니다: `kubectl -n automachine get deploy -L automachine/env`
- 파드가 늘어도 메모리는 웹 약 10MB, AI 분석 약 100MB씩만 더 씁니다.
- 11/3 시험: 웹 파드 2개일 때 하나를 지워도 0.5초마다 16번 요청이 모두 200이었습니다. dev로 돌아오면 파드 수와 채점 예약도 원래대로 돌아왔습니다.

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

## HMI 설정

HMI의 [설정] 메뉴에서 바꾼 장비 설정(로트 크기, 중량 검사 주기, 진공 기준 등)과 자동 로그아웃 시간은 이 PC의 `state/machine_settings.json`에 저장돼, 시뮬레이터 파드를 다시 띄워도 남습니다. 표준값과 다른 것만 적고, 파일을 지우면 출하값으로 돌아갑니다. 평가용 런(`eval/make_runs.py`, 매일 자동 채점)은 이 파일을 읽지 않습니다. 운전 방식(드라이·더미 런)은 저장하지 않으므로 재시작하면 자동 운전입니다. 화면 설정(언어, 테마, 글자 크기)은 각 브라우저에만 저장됩니다.

## 채점

```bash
ANALYSIS_API=http://127.0.0.1/api/analysis/runs/ python3 eval/score.py --split dev
```

공정 채점과 반장 채점은 analysis 파드 안에서 학습을 돌리므로 `ANALYSIS_EXEC`도 필요합니다. 공정 채점은 약 1분 동안 파드 CPU를 많이 써서 HPA가 파드를 늘릴 수 있습니다.

```bash
export ANALYSIS_API=http://127.0.0.1/api/analysis/runs/
export ANALYSIS_EXEC="kubectl -n automachine exec -i deploy/analysis --"
python3 eval/compare.py
python3 eval/score_foreman.py   # 사건마다 LLM을 불러 오래 걸립니다. 끊겼으면 --reuse
```

## 분류와 반장

분류 모델(`analysis/app/classifier.json`)은 이미지에 들어갑니다. 매뉴얼은 `deploy.sh`가 배포 때마다 `manual_chunks`에 다시 넣습니다. 이때 Ollama가 꺼져 있으면 경고만 내고 넘어가므로, 나중에 다시 넣습니다.

```bash
kubectl -n automachine exec deploy/analysis -- python -m app.manual
```

반장 보고서는 한 건에 1분 안팎 걸립니다. Ollama가 꺼져 있으면 보고서만 503으로 실패하고, 규칙·경비원·분류는 그대로 동작합니다. 모델은 `LLM_MODEL` 환경 변수로 바꿉니다. GPU는 k8s가 나눠 주지 못하므로 medi-info 평가와 시간을 겹치지 않게 돌립니다.

## 운영 화면

http://127.0.0.1/#ops 에서 노드, GPU, LLM 상태와 서비스 상태판, 매일 자동 채점 결과, 배포 현황, 이벤트, 로그를 봅니다. "파드 죽이기"를 누르면 복구 과정이 기록됩니다.

```bash
# 버튼에 필요한 운영 토큰 보기
kubectl -n automachine get secret ops-token -o jsonpath='{.data.token}' | base64 -d; echo
```

| 버튼 | 같은 명령 | 대상 |
|---|---|---|
| 파드 죽이기 | `kubectl delete pod` | web, analysis |
| 재시작 | `kubectl rollout restart` | web, analysis |
| 되돌리기 | `kubectl rollout undo` | web, analysis |
| 지금 채점 | `kubectl create job --from=cronjob/auto-eval` | auto-eval |

- 이 PC 안에서만 열립니다. 다른 주소로 들어오면 Traefik이 403을 돌려주고, Tailscale Funnel 요청은 ops가 거절합니다.
- 바꿀 수 있는 건 web과 analysis뿐입니다. db는 전체가 멈추고, sim은 돌던 장비 상태가 사라지기 때문입니다.
- 재시작도 새 배포 번호를 하나 만듭니다. 그래서 재시작 직후의 되돌리기는 재시작 전과 같은 버전으로 돌아갑니다.
- ops 계정(`k8s/app/ops.yaml`)은 Secret을 읽거나 exec할 수 없습니다. 쓰기 권한은 파드 삭제, web과 analysis Deployment 변경, 작업(Job) 생성입니다.
  작업 생성은 k8s에서 이름으로 제한할 수 없어, 계정이 털리면 이 네임스페이스에 아무 작업이나 만들 수 있습니다. 코드는 auto-eval 설정만 복사합니다.
- GPU 수집기(`gpu-metrics`)는 WSL 제약으로 특권 파드입니다. 그래서 ops와 분리했고 k8s 계정을 주지 않았습니다.
- 메모리 값은 k8s 측정값이라 캐시 일부가 포함되어, `free`의 used보다 크게 나옵니다. Windows 전체 메모리는 보이지 않습니다.

## 서비스 요청 지표

운영 화면의 "서비스 요청"은 초당 요청, 5xx·4xx 수, 응답 시간을 서비스별로 보여 줍니다. WSL 메모리를 아끼려고 Prometheus 없이, ops가 Traefik의 지표(`:9100/metrics`)를 15초마다 읽어 최근 5분을 메모리에 들고 있습니다.

- ops가 재시작하면 기록이 사라지고 다시 쌓입니다.
- Traefik을 거친 요청만 셉니다. 파드끼리의 요청과 부하 시험은 빠집니다.
- 응답할 파드가 하나도 없을 때의 503은 서비스별 숫자에 남지 않아서, 입구 기준인 "전체" 줄에서 봅니다. "전체"에는 같은 Traefik을 쓰는 medi-info도 포함됩니다.
- 응답 시간은 Traefik의 칸(0.1, 0.3, 1.2, 5초)으로만 알 수 있어서, 정확한 값이 아니라 "95%가 이 시간 안에 들었다"로 표시합니다.

## 자동 확장 (HPA)

analysis는 파드 평균 CPU가 요청량(100m)의 50%를 넘으면 최대 3개까지 늘고, 부하가 사라지고 1분이 지나면 다시 줄어듭니다. 운영 화면의 "부하 시작"으로 볼 수 있습니다. 토큰이 필요하고 150초 뒤 저절로 끝납니다.

부하 시험은 가벼운 `/api/analysis/live`만 호출합니다. 확장 동작을 보여 주기 위한 것으로, 실제 분석 작업의 성능 측정이 아닙니다.

## 실시간 감시

`watch` 파드(분석 이미지, `app/watch.py`)가 시뮬레이터에 지금 런을 묻고, 그 로그를 3초마다 이어 읽어 규칙·경비원·분류·판단 코드를 돌립니다.
경보는 모든 탭 위의 청록색 띠와 AI 분석 탭의 "실시간 감시" 패널에 나오고, 관련 설비 알람보다 몇 분 먼저였는지도 보여 줍니다.

- 파드는 1개입니다. 경보를 메모리에 두기 때문에 여러 개면 파드마다 목록이 달라집니다. 재시작하면 로그를 처음부터 다시 읽습니다.
- DB를 쓰지 않습니다. "보고서 쓰기"를 누를 때만 지금 런을 적재(`POST /api/analysis/runs/<런>/ingest`)하고 반장이 보고서를 씁니다.
- 그 시점까지의 기록만 쓰므로 노즐 막힘은 청소한 뒤 온도 센서로 바뀔 수 있습니다.
- 재생 시험: `bash eval/explore/live_replay.sh <런 ID>`. 끝난 런을 5분씩 흘려 넣어 경보 시점과 알람보다 앞선 시간을 봅니다. 11/3 dev 런 4개(사건 8개)에서 마지막 원인이 분석 버튼과 모두 같았고, 2~55분 먼저였습니다.
- Compose에는 없습니다 (k8s 전용).

## 매일 자동 채점

CronJob `auto-eval`이 매일 21:00(한국 시각)에 새 런 3개를 만들어 적재하고 채점합니다. 결과는 이 PC의 `scores/auto_<날짜>.json`에 남습니다.
낮에는 medi-info를 켜고 k3s를 꺼 두므로 저녁으로 정했습니다(11/4, 원래 13:00). 21:00에 k3s가 꺼져 있었으면 다음 날 21:00 전까지 k3s를 켜는 순간 한 번 실행됩니다(`startingDeadlineSeconds` 23시간).
날짜는 실행한 날 기준이라, 하루에 두 번 돌아도 런은 새로 만들지 않고 채점만 다시 합니다. 켜자마자 따라잡기가 돌면 파드가 뜨는 것과 겹쳐 잠깐 메모리를 많이 씁니다.

| 단계 | 이미지 | 하는 일 | 정답지 |
|---|---|---|---|
| make-runs | sim | 시나리오 11개 중 그날의 3개를 날짜로 정한 시드로 생성 (`eval/auto_runs.py`) | 씀 |
| ingest | analysis | 새 런을 DB에 적재 | 연결 안 함 |
| score | sim | 분석 API의 답을 정답지와 비교 (`eval/auto_score.py`) | 읽기만 |

```bash
# 지금 바로 실행 (같은 날 다시 실행하면 런은 새로 만들지 않고 채점만 다시 함)
kubectl -n automachine create job --from=cronjob/auto-eval auto-eval-$(date +%m%d%H%M)
kubectl -n automachine logs job/<위 이름> -c score
```

- 한 번에 약 50초, 런 하나는 로그 약 30MB, DB 약 30MB입니다. 로그와 DB는 자동으로 지우지 않습니다.
- 규칙, 경비원, 경비원 + 분류, 코드 판단만 채점합니다. LLM은 GPU를 오래 써서 부르지 않고, 원인 점수에도 영향이 없습니다.
- 이 런들은 `eval/runs.csv`에 없어서 dev/test 채점에는 섞이지 않습니다. 규칙과 기준을 만든 뒤에 생긴 런이므로 처음 보는 시험으로 볼 수 있습니다.

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

WSL mirrored 네트워크에서는 PC에서 Service 주소로 들어가는 경로가 시간 초과로 막힙니다 (파드에서 Service로, PC에서 파드 IP로는 됩니다). 그래서 `cluster/traefik-config.yaml`로 Traefik이 80을 직접 엽니다. k3s가 켜져 있는 동안 80, 8444, 8088, 9100번을 씁니다. https 입구(`websecure`)는 쓰지 않아서 443이 아니라 8444에 둡니다. 443을 잡으면 이 PC에서 medi-info의 Tailscale Funnel 주소(https)를 열 때 Tailscale 대신 Traefik이 자체 인증서로 대답해서 인증서 경고가 났습니다 (11/09).

Ollama는 GPU를 쓰므로 클러스터 밖 WSL에서 돌고, 파드에서는 `ollama` Service를 거쳐 `10.42.0.1:11434`로 연결합니다.

## 외부 공개 (Tailscale Funnel)

`.env`에 `FUNNEL_HOST=<이 PC>.ts.net`이 있으면 `deploy.sh`가 그 주소용 Ingress(`automachine-funnel`)를 만듭니다. 주소는 이 PC 것이라 저장소에 적지 않습니다.

```bash
# Windows PowerShell에서 Funnel 켜기 (Traefik 80번으로)
tailscale funnel --bg 80
# WSL에서: 이 주소를 automachine이 받게 (medi-info와 같은 주소를 씀)
k3s-switch automachine
k3s-switch status        # Funnel 주소 automachine-funnel: 켜짐
# 끝나면 Windows PowerShell에서
tailscale funnel reset
```

- medi-info도 같은 Funnel 주소를 씁니다. k3s의 Traefik은 파드가 0개인 Ingress도 골라 503을 내므로, `k3s-switch`(이 PC의 `~/.local/bin`)가 자는 쪽의 `.ts.net` Ingress를 없는 IngressClass(`sleeping`)로 바꿔 Traefik이 무시하게 합니다. 이 Ingress에는 `ingressClassName`을 적지 않아서, 다시 배포해도 `k3s-switch`가 정한 값이 유지됩니다.
- 시뮬레이터 API에는 인증이 없어서, 공개하면 밖에서도 장비 조작과 고장 주입이 됩니다. 발표·시연 때만 켭니다.
- 운영 API는 Funnel 요청(`Tailscale-Funnel-Request` 헤더)을 거절합니다.
- 이 PC에서 자기 `.ts.net` 주소를 열면 tailnet IP로 풀려 Funnel을 거치지 않습니다 (헤더가 없어 운영 API도 열림). 진짜 외부 동작은 다른 네트워크의 기기로 확인합니다.

## 아직 확인하지 못한 것

- 네트워크가 바뀌어 노드 IP(현재 Wi-Fi)가 달라졌을 때의 동작 (리허설 전에 확인)
- Funnel을 다른 네트워크의 기기(휴대폰 LTE)에서 열었을 때의 동작과 운영 API 403 (이 PC에서는 화면·API 200, 웹소켓 101까지 확인)
