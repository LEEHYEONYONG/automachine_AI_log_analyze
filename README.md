# automachine — 가상 디스펜싱 장비

스마트폰 조립 라인의 **디스펜싱(접착제 도포) 셀**을 Python으로 시뮬레이션해서,
실제 장비처럼 로그를 남기고 숨겨진 고장을 주입하는 프로젝트입니다.
생성된 로그는 AI 로그 분석의 입력이 되고, 고장 정답(ground truth)은 분석 결과를 평가하는 데 쓰입니다.

## 실행

Python 3.11 이상이 필요합니다. 처음 한 번 가상환경을 만들고 활성화하세요.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # PowerShell (Git Bash: source .venv/Scripts/activate)
```

```bash
python run_sim.py config/scenarios/normal.json            # 정상 8시간 가동
python run_sim.py config/scenarios/nozzle_clog.json       # 노즐 막힘
python run_sim.py config/scenarios/vacuum_leak.json       # 디스펜서 진공 지그 패드 누설
python run_sim.py config/scenarios/temp_sensor_drift.json # 시린지 온도 센서 드리프트
python run_sim.py config/scenarios/normal.json --hours 1 --seed 7

python -m unittest -v                                     # 테스트
```

8시간 가동 시뮬레이션은 약 2초가 걸립니다.

## Docker로 실행 (WSL)

WSL Ubuntu에 Docker Engine이 있으면 시뮬레이터, 화면, 분석 서버, DB를 한 번에 띄울 수 있습니다.
처음 한 번 `.env`를 만들고 `DB_PASS`를 채우세요.

```bash
cp .env.example .env              # DB_PASS 입력
docker compose up --build         # 처음, 또는 Dockerfile·requirements가 바뀌었을 때
docker compose up                 # 평소
```

| 서비스 | 주소 | 내용 |
|---|---|---|
| web | http://localhost:5174 | HMI, 엔지니어 콘솔, 3D 뷰어 (Vite dev) |
| sim | http://localhost:8100 | 시뮬레이터 서버 (`server/`), `logs/`와 `ground_truth/`에 기록 |
| analysis | http://localhost:8101/docs | 로그 분석 서버 (`analysis/`), `/api/analysis/health` |
| db | localhost:5433 | PostgreSQL 17 + pgvector |
| Ollama | WSL의 11434 | Docker 밖 systemd 서비스. analysis는 `host.docker.internal`로 접속 |

포트는 medi-info(5432/8000/5173)와 겹치지 않게 정했습니다. 코드를 고치면 sim, analysis, web 모두 자동으로 다시 로드됩니다.

- **analysis 컨테이너에는 `logs/`만 읽기 전용으로 연결**하고 `ground_truth/`는 연결하지 않습니다. 분석기가 정답을 볼 수 없게 하기 위해서입니다.
- 로그를 DB에 적재: `docker compose exec analysis python -m app.ingest` (전체) 또는 `... python -m app.ingest <run_id>`. 같은 실행을 다시 적재하면 덮어씁니다. `io_trace.csv`는 파일로 둡니다.
- 테스트: `docker compose exec sim python -m unittest -v`
- DB 접속: `docker compose exec db psql -U automachine -d automachine`
- 스키마(`db/init/`)는 DB 볼륨을 처음 만들 때만 실행됩니다. 바꾼 뒤에는 `docker compose down -v`로 볼륨을 지우고 다시 올리세요(적재한 데이터도 지워집니다).

## 실시간 실행 (HMI)

Python 패키지와 Node.js 22.12 이상이 필요합니다(Vite 8 요구 사항).

```powershell
pip install -r requirements-dev.txt
cd web; npm install; npm run build; cd ..
python -m server                  # http://127.0.0.1:8000 에서 HMI가 열립니다
```

화면을 수정하면서 개발할 때는 서버를 켜 둔 상태에서 `cd web; npm run dev`를 실행하고 http://localhost:5173 을 엽니다.
API와 WebSocket 요청은 8000번 포트로 프록시됩니다.

- 서버는 새 실행을 **정지 상태**로 시작합니다. HMI 하단의 START를 눌러 가동하세요.
- 오른쪽 위 점선 상자 **SIM**은 장비가 아니라 시뮬레이터 조작입니다. 배속(×1~×300), 일시정지, 자동 작업자를 바꿉니다.
- **자동 작업자**를 끄면 알람에 직접 대응해야 합니다. 정지 상태에서 [유지보수] 메뉴의 조치를 한 뒤 RESET, START 순서로 재가동합니다. 휴식과 모델 체인지도 자동 작업자가 할 때만 일어납니다.
- 실시간 실행 로그도 `logs/<run_id>/`에 1초마다 기록됩니다.

### HMI 메뉴

오퍼레이터가 장비 앞에서 보는 화면을 흉내 냈습니다. 왼쪽 메뉴로 화면을 바꾸고, 하단의 **START / CYCLE STOP / STOP / RESET**은 어느 화면에서나 보입니다.
CYCLE STOP은 라인에 있는 제품을 다 처리한 뒤 서고, STOP은 즉시 섭니다. 알람이 나면 모든 화면 위에 알람 바가 뜨고, 누르면 알람 화면으로 갑니다.

| 메뉴 | 내용 |
|---|---|
| 메인 | 스테이션별 현재 스텝, 진행률, 대기 사유(다음 스테이션 대기, 이전 공정 대기 등), 생산 수량, UPH, 택트 타임, 자재, 센서, **실시간 로그** |
| 시퀀스 | 스테이션별 **표준 시퀀스**(스텝, 동작, 기준 시간, 실행 조건)와 현재 스텝, 최근 스텝 실적. 기준보다 20% 이상 느린 스텝은 강조됩니다. |
| 수동 | MANUAL 모드에서 실린더(스토퍼, 리프트, 푸셔, 픽커), 진공, 컨베이어를 하나씩 조작하고 서보축(디스펜서 X/Y/Z, 스캔 축, NG 픽커 Y)을 조그·프리셋으로 이동합니다. 센서 램프, 진공값, 축 위치가 표시되고 **인터록**이 위험한 조작을 막습니다. |
| I/O | PLC 방식의 입력(X)·출력(Y) 신호 모니터. 8진수 주소, 신호 이름, ON/OFF, 마지막 변화 시각. 비상정지·도어·메인 에어 압력 스위치, SMEMA 핸드셰이크, 제품 감지, 실린더 위치 센서, 진공 스위치, 축 INPOS와 솔레노이드·모터·밸브·조명·레이저 출력을 보여 주고, MANUAL에서는 장치가 연결된 출력을 **강제 출력**할 수 있습니다(인터록 적용). |
| 알람 | 현재 알람의 **추정 원인과 조치 방법**(E4001은 불량 유형별), 알람 이력과 정지 시간, 발생 빈도 |
| 로그 | 이벤트 / 알람 / 생산 로그 검색 (레벨, 유닛, 검색어 필터, 자동 갱신) |
| 생산 | 생산 현황, 가동·대기·정지·알람 시간 분석, 공정 트렌드 그래프 |
| 레시피 | 레시피 A/B의 항목별 값, 허용 범위, **현재 운전 설정값**(레시피와 다르면 강조)과 변경 이력. 메이커는 값을 편집하고(범위 검사), 엔지니어는 정지 상태에서 로드(모델 체인지)합니다. 레시피를 바꾸면 실제 결과도 바뀝니다: 토출 유량, 비드 폭, 점도는 전원 투입 때 검증된 레시피 기준의 물리로 계산되므로, 예를 들어 압력을 8% 올리면 토출량도 약 8% 늘어납니다. 편집 내용은 서버 실행 동안만 유지되고 `Recipe edited` 로그로 남습니다. |
| 유지보수 | 노즐 청소, 퍼지, 니들 캘리브레이션, 시린지 교체 등 조치 버튼 (정지 상태에서만) |

주소로 화면을 바로 열 수 있습니다. 예: `#hmi/sequence/DISPENSER`, `#hmi/log`

**원점 복귀**: 전원 투입(서버 시작, 새 실행) 후와 MANUAL에서 장치를 움직인 뒤에는 하단의 [원점 복귀]를 해야 START할 수 있습니다. 안전 확인 → 진공 해제 → 푸셔 후진·픽커 상승 → 리프트 하강 → 스토퍼 상승 → Z축 → X/Y축 → 보조축 원점 → 재공품 확인 순서로 진행되고 단계마다 로그가 남습니다. 라인에 제품이 있으면 재공품 유지(작업 중이던 스테이션은 다시 시작, 도포가 시작된 제품은 INIT_INCOMPLETE로 NG) 또는 재공품 제거(SCRAP_INIT)를 고릅니다. 자동 작업자는 필요하면 원점 복귀 후 START합니다. API: `POST /api/initialize {clear_parts}`

**비상정지와 안전 도어**: HMI 하단 왼쪽의 빨간 **비상정지** 버튼은 누구나 누를 수 있습니다. 누르면 E9100으로 모든 동작이 즉시 서고, 토출 밸브와 진공 같은 출력이 꺼지며, 서보 전원이 끊긴 것으로 보고 다시 원점 복귀가 필요해집니다(원점 복귀 중이었다면 중단). 해제하기 전에는 RESET이 거부됩니다. 전면 좌·우 안전 도어는 사람이 직접 여는 것이라 **엔지니어 콘솔의 현장 조작** 패널에서 엽니다. 운전 중에 열면 E9101로 즉시 정지하고, 열려 있는 동안 START와 원점 복귀가 거부됩니다(MANUAL 정비 중에는 열 수 있음). I/O의 비상정지·도어 입력과 3D 뷰어(도어가 열리고 비상정지 버튼이 빛남)에 반영되고, 자동 작업자는 비상정지나 도어가 풀린 뒤에야 RESET → 원점 복귀 → START로 재가동합니다. API: `POST /api/safety/estop {pressed}`, `POST /api/safety/door {door, open}`

**로그인과 권한**: 오른쪽 위에서 로그인합니다(사용자와 PIN은 `config/hmi_users.json`, 10분 동안 조작이 없으면 자동 로그아웃). 권한은 서버가 검사하고, 거부되면 `Access denied`가 로그에 남습니다. 로그의 `by=`에는 로그인한 사용자 ID가 기록됩니다.

| 권한 | 할 수 있는 것 |
|---|---|
| 게스트 (로그인 전) | 화면 보기, STOP, CYCLE STOP (정지는 항상 허용) |
| 오퍼레이터 (OP01 / 1111) | START, RESET, 원점 복귀, 일반 유지보수 |
| 엔지니어 (ENG01 / 2222) | MANUAL 모드와 수동 조작, I/O 강제 출력, 니들 캘리브레이션, 진공 패드 교체, 레시피 로드(모델 체인지) |
| 메이커 (MAKER / 9999) | 레시피 값 편집 |

SIM 바, 엔지니어 콘솔, 자동 작업자는 시뮬레이터 도구라서 권한과 무관합니다.

**AUTO / MANUAL**: 하단 왼쪽 스위치로 바꿉니다.

- MANUAL로는 운전 중이 아닐 때만 바꿀 수 있고, MANUAL에서는 START가 막힙니다.
- AUTO로 돌아가려면 모든 장치가 자동 운전 원위치(리프트 하강, 푸셔 후진, 스토퍼 상승, 진공 OFF, 축 원점)에 있어야 합니다. [수동] 화면의 **전체 원위치**는 충돌하지 않는 순서(진공 OFF·푸셔 후진 → 리프트 하강, Z 상승 → X/Y 원점)로 장치를 돌려놓습니다.
- 실린더는 스트로크 시간이 지나야 도착 센서가 켜지고, 공장 에어가 약하면 느려집니다. 지그 진공은 지그 위에 제품이 앉아 있을 때만 올라갑니다.
- 주요 인터록: 리프트가 올라가야 푸셔 전진, 푸셔가 후진해야 리프트 하강, Z축이 안전 높이(80 mm) 이상이어야 X/Y 이동, 니들은 올라간 제품 위나 저울 위에서만 하강, NG 픽커는 내려간 상태에서 Y 이동 불가.
- 수동 조작, 인터록 거부, 모드 전환은 모두 `event.log`에 남고, 3D 뷰어에도 그대로 반영됩니다. 자동 작업자는 MANUAL 동안 아무것도 하지 않습니다.
- MANUAL에서 장치를 움직였다면 AUTO로 돌아온 뒤 원점 복귀가 필요합니다.

[생산] 메뉴의 **공정 트렌드**에는 weight check 토출량, 비드 폭, 비드 위치 오차, 지그 흡착 진공, 시린지 온도, 토출 압력이
제품별 측정값으로 그려집니다(최근 10분 / 1시간 / 8시간, 구간이 길면 평균). 상한·하한 기준선이 함께 표시되어
고장 징후가 기준선에 다가가는 모습을 볼 수 있습니다.

**3D 뷰어** 탭에서는 장비가 실제 스텝에 맞춰 움직입니다. 외부 모델 파일 없이 코드로 만든 장면입니다.

- 프로파일 프레임과 안전 커버(토글 가능), 하부 캐비닛, 비상정지 버튼, HMI 패널, 시그널 타워
- 스테이션마다 독립된 **듀얼 레인 컨베이어 구간**: 제품이 들어오거나 나갈 때만 해당 구간 벨트가 돕니다. 구간마다 스토퍼 핀과 제품 감지 센서가 있습니다.
- 양옆의 **이전 공정 / 다음 공정 컨베이어**: 이전 공정이 준비되면 제품을 받고, 다음 공정이 받을 수 있을 때 넘깁니다.
- 투입부: 2D 코드 리더
- 비전 정렬: 레인 사이의 **리프트**가 제품을 들어 올리고, **푸셔 두 개**가 기준 핀 쪽으로 밀어 정렬한 뒤 촬영합니다. 남은 미세 오차는 디스펜서가 도포 경로에서 보정합니다.
- 디스펜서: 리프트와 **진공 지그**로 제품을 고정하고 도포합니다. 시린지(접착제 잔량, 플런저, 어댑터 캡, 니들 허브), 에어 호스, 컨트롤러, 바람막이 달린 저울, 높이 측정 레이저가 있습니다.
- 도포 검사: 라인 스캔 카메라와 라인 레이저가 짧은 축을 따라 제품 위를 훑습니다.
- 배출부: OK 제품은 다음 공정으로 넘기고, NG 제품은 진공 픽커가 NG 버퍼로 옮깁니다.

오른쪽 위 버튼으로 **전체 / 투입부 / 비전 정렬 / 디스펜서 / 배출부** 시점을 바꿀 수 있습니다(`?view=vision#3d`처럼 주소로도 가능).
×1~×10 배속에서 자연스럽게 보입니다. 주소에 `#hmi`, `#console`, `#3d`를 붙이면 해당 탭이 바로 열립니다.

**엔지니어 콘솔** 탭에서는 다음을 할 수 있습니다. 고장 정답이 보이는 화면이므로, AI 분석 결과는 이 화면을 보기 전에 기록해 두세요.

- 시나리오를 골라 새 실행 시작
- 고장 종류와 파라미터를 정해 지금 또는 N분 뒤에 주입
- 고장 상태(예약됨, 진행 중, 해결됨), 진행률, 해결 조치 확인
- 센서에 보이지 않는 실제 물리 상태 확인 (노즐 개방률, 누설률, 실제 온도와 HMI 표시 온도 비교 등)
- 정답 파일(`ground_truth/<run_id>/faults.json`)은 실행 중에도 1초마다 갱신됩니다.

| API | 설명 |
|---|---|
| `GET /api/state`, `WS /ws` | 장비 상태 (WebSocket은 0.1초마다 전송) |
| `POST /api/machine/{start\|cycle_stop\|stop\|reset}` | 운전 명령 |
| `GET /api/logs?kind=event&level=INFO&unit=&q=` | 최근 로그 조회 (event / alarm / production, 최신순) |
| `POST /api/login` `{user, pin}`, `POST /api/logout` | HMI 로그인 / 로그아웃 |
| `POST /api/opmode` `{mode}` | AUTO / MANUAL 전환 (불가하면 409와 이유) |
| `POST /api/manual/device` `{device, on}` | 실린더·진공·벨트 조작 (인터록에 걸리면 409와 이유) |
| `POST /api/manual/axis` `{axis, jog \| preset \| move_to}` | 서보축 조그, 프리셋, 절대 위치 이동 |
| `POST /api/manual/home_all` | 전체 원위치 |
| `GET /api/recipes`, `POST /api/recipes/{name}` `{values}`, `POST /api/recipes/{name}/load` | 레시피 조회, 편집(메이커), 로드(엔지니어) |
| `GET /api/io` | I/O 입력·출력 신호 현재값 |
| `POST /api/io/force` `{address, value}` | 출력 강제 (MANUAL에서, 장치가 연결된 출력만) |
| `POST /api/maintenance` `{action}` | 유지보수 조치 (정지 상태에서만) |
| `POST /api/operator` `{auto}` | 자동 작업자 켜기/끄기 |
| `POST /api/sim` `{speed, paused}` | 배속, 일시정지 |
| `POST /api/runs` `{scenario}` | 새 실행 시작 (시나리오 생략 시 고장 없는 live 실행) |
| `POST /api/faults` `{type, params, delay_min}` | 고장 주입 (엔지니어 콘솔용) |
| `GET /api/trends?minutes=60` | 공정 트렌드 데이터 (계열당 최대 300포인트) |
| `GET /api/meta` | 시나리오, 고장 종류와 기본 파라미터, 조치 목록, 알람 코드 |

## 장비 구성

인라인 설비입니다. 이전 공정에서 하우징을 받아 도포한 뒤 다음 공정으로 넘깁니다.

```
이전 공정 ⇒ [INFEED] → [VISION] → [DISPENSER] → [INSPECTION] → [OUTFEED] ⇒ 다음 공정
            핸드셰이크   리프트 +      리프트 + 진공 지그   라인 스캔으로      OK: 다음 공정으로
            2D 코드 판독  푸셔 정렬    비드 도포            비드 폭/위치 검사   NG: 픽커 → NG 버퍼
                                     + 주기적 weight check
```

- 스테이션마다 컨베이어 구간이 따로 있어서, 각 제품이 독립적으로 멈추고 이동합니다.
- 리프트, 푸셔, 스토퍼 같은 **에어 실린더 동작은 공장 에어가 약해지면 느려집니다.** 이 차이는 `event.log`의 스텝 시간(`t=`)에 나타납니다.
- 이전 공정 공급 지연(`Waiting for upstream`)과 다음 공정 막힘(`Waiting for downstream`)도 로그에 남습니다. 가동률 손실 분석에 쓸 수 있습니다.
- 각 스테이션은 상태 머신(IDLE → BUSY → DONE / ALARM)이고, 공정 시퀀스는 PLC 스텝처럼 순서대로 작성되어 있습니다(`simulator/stations/`).
- 알람이 나면 장비가 멈추고, **가상 작업자**(`simulator/operator.py`)가 일정 시간 뒤 알람을 확인하고 조치한 다음 리셋하고 재가동합니다.
  같은 알람이 반복되면 조치 단계를 올립니다(예: 노즐 청소 → 시린지 교체 → 엔지니어 호출).
- 장비 사양과 레시피는 `config/machine.json`, 시나리오는 `config/scenarios/*.json`에 있습니다.

## 출력 파일

| 경로 | 내용 | 용도 |
|---|---|---|
| `logs/<run_id>/event.log` | 스텝, 측정값, 작업자 조치 텍스트 로그 | 분석 입력 |
| `logs/<run_id>/alarm.log` | 알람 SET/CLEAR 이력 | 분석 입력 |
| `logs/<run_id>/sensor_trend.csv` | 1초 주기 센서값 (진공, 압력, 온도, 시린지 잔량) | 분석 입력 |
| `logs/<run_id>/production.csv` | 제품별 측정값과 판정 | 분석 입력 |
| `logs/<run_id>/io_trace.csv` | I/O 신호가 바뀔 때마다 한 줄 (시각, 주소, 신호, 값). 실린더 솔레노이드 ON부터 센서 ON까지의 시간 등을 계산할 수 있습니다. 8시간에 약 30만 줄 | 분석 입력 |
| `logs/<run_id>/machine_info.json` | 장비 ID, 레시피, 계획 휴식 시간, 알람 코드표, I/O 맵 | 분석 입력 |
| `ground_truth/<run_id>/faults.json` | 모든 고장(주입, 자연 발생, 작업자 실수)과 발생 원인, 발생/해결 시각, 해결 조치 | **평가 전용** |
| `ground_truth/<run_id>/hidden_state.csv` | 10초 주기 실제 물리 상태 (공장 에어, 노즐 개방률, 니들 오차, 기포, 실제 온도 등) | **평가 전용** |

`run_id`는 시나리오 이름을 드러내지 않도록 만들어집니다. 로그 안에도 고장 정보가 없습니다(테스트로 확인).

## 고장 시나리오

실제 에어 펄스(시린지) 디스펜서 경험을 바탕으로 만든 고장들입니다.

| 고장 | 숨겨진 원인 | 로그에 나타나는 징후 | 해결 |
|---|---|---|---|
| `nozzle_clog` | 노즐 내부 경화로 유로가 좁아짐 | weight check 값 하락 → E3005, 비드 폭 감소 | 노즐 청소 |
| `vacuum_leak` | 디스펜서 진공 지그 패드 마모로 누설 | 지그 진공값이 임계치로 접근 → 재안착(RESEAT) 재시도 → E3001 반복 | 진공 패드 교체 |
| `temp_sensor_drift` | 온도 센서가 높게 읽어서 실제로는 덜 가열됨 | **표시 온도는 정상**, weight check 하락 → E3005가 노즐 청소나 시린지 교체로 안 고쳐짐 | 엔지니어 교정 |
| `air_bubble` | 시린지 안 기포 (시린지 교체 때 자연 발생하기도 함) | 띄엄띄엄 나오는 `BEAD_VOID` 불량, weight check 편차 증가 | 퍼지, 시린지 교체, 또는 기포가 다 빠지면 저절로 해소 |
| `needle_tip_buildup` | 니들 바깥에 접착제가 쌓여 들어 올릴 때 실이 생김 | `STRINGING` 불량 증가, weight와 폭은 정상 | 노즐 청소 |
| `needle_offset` | 니들 높이/위치가 티칭 값에서 틀어짐 (**높이 레이저는 제품 표면만 재서 못 봄**) | 비드 폭이나 위치가 계단처럼 변함, `BEAD_OFFSET` | 니들 캘리브레이션 |
| `air_supply_drop` | 공장 에어 공급압 일시 저하 | **토출 압력, 지그 진공, 실린더 동작 속도가 동시에** 나빠짐, E3005, 진짜 조치 없이 회복 | 저절로 회복 |
| `recipe_pressure_error` | 레시피 압력 오입력 | event.log의 `Recipe parameter changed` 직후 토출량이 계단처럼 변함 | 엔지니어(레시피 복구), 모델 체인지 |
| `recipe_retract_error` | 니들을 들기 전 dwell을 0으로 입력 | `DWELL` 스텝이 사라지고 `STRINGING` 급증 | 엔지니어, 모델 체인지 |

### 운영 요소

- **휴식과 교대**: `config/machine.json`의 `plant.breaks`에 따라 10:00, 12:00~13:00, 15:00 등에 사이클 정지(라인을 비운 뒤 정지)하고, 휴식이 끝나면 재가동합니다. 휴식 중에 난 알람은 휴식이 끝날 때까지 기다립니다. 08:00과 20:00에 작업자 조가 바뀝니다.
- **가사시간(pot life)**: 시린지를 장착한 뒤 시간이 지날수록 점도가 올라 토출량이 조금씩 줄어듭니다. 6시간이 지나면 E3006 알람이 나고 시린지를 교체합니다. 재료 로트마다 점도도 조금씩 다릅니다.
- **모델 체인지**: 시나리오의 `schedule`이나 엔지니어 콘솔에서 레시피 B로 바꿉니다. 셋업에 15~25분이 걸리고, 새 로트가 시작되며, 디스펜스 위치 오차가 생길 수 있습니다.
- **작업자 판단과 실수**: 작업자는 E4001이 나면 불량 유형을 보고 조치를 고릅니다(BEAD_VOID → 퍼지, BEAD_OFFSET → 캘리브레이션 등). 가끔 조치 없이 리셋만 하고, 노즐 청소 뒤 캘리브레이션을 빠뜨리고, 모델 체인지 때 레시피 값을 잘못 넣습니다.
- **고장 발생 원인 기록**: 자연 발생 고장과 작업자 실수도 정답 파일에 `origin`과 함께 기록됩니다(`injected`, `natural: ...`, `operator_error: ...`).

정상 가동 중에도 시린지 교체(E3003/E3006), 간헐적인 비전 인식 실패(E2001), 2D 코드 판독 실패(E1001), NG 버퍼 가득 참(E5001) 같은 일상적인 알람과 앞뒤 공정 대기가 섞여 나옵니다.

`config/scenarios/realistic_day.json`은 위 요소가 모두 섞인 12시간 시나리오입니다. 휴식, 레시피 B로의 모델 체인지, 에어 저하, 니들 끝 누적에 더해 실행마다 다른 자연 발생 고장과 작업자 실수가 포함됩니다.

새 고장은 `faults/library.py`에 `Fault`를 상속한 클래스를 추가하고 `FAULT_TYPES`에 등록하면 됩니다.

## 폴더 구조

```
config/          장비 설정, 시나리오
simulator/       시뮬레이터 (clock, physics, sensors, stations, machine, operator, simulation)
faults/          고장 엔진과 고장 라이브러리
server/          FastAPI 실시간 서버 (시뮬레이터 구동, REST + WebSocket)
web/             React 19 + Vite 8, JavaScript (HMI, 엔지니어 콘솔, 3D 뷰어). 검사: npm run lint
analysis/        AI 로그 분석 서버 (FastAPI). 로그 적재는 app/ingest.py, 분석 코드는 직접 구현
eval/            분석 결과 평가 (직접 구현)
docs/references/ 참고 매뉴얼 보관 (git 제외)
db/init/         PostgreSQL 스키마 (DB 볼륨을 처음 만들 때 실행)
tests/
```

## 다음 단계

1. 공개 매뉴얼을 참고해서 파라미터와 알람 체계 다듬기
