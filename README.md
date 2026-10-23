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
python run_sim.py config/scenarios/vacuum_leak.json       # 로더 흡착 패드 누설
python run_sim.py config/scenarios/temp_sensor_drift.json # 시린지 온도 센서 드리프트
python run_sim.py config/scenarios/normal.json --hours 1 --seed 7

python -m unittest -v                                     # 테스트
```

8시간 가동 시뮬레이션은 약 2초가 걸립니다.

## 실시간 실행 (HMI)

Python 패키지와 Node.js 20 이상이 필요합니다.

```powershell
pip install -r requirements-dev.txt
cd web; npm install; npm run build; cd ..
python -m server                  # http://127.0.0.1:8000 에서 HMI가 열립니다
```

화면을 수정하면서 개발할 때는 서버를 켜 둔 상태에서 `cd web; npm run dev`를 실행하고 http://localhost:5173 을 엽니다.
API와 WebSocket 요청은 8000번 포트로 프록시됩니다.

- 서버는 새 실행을 **정지 상태**로 시작합니다. HMI에서 START를 눌러 가동하세요.
- 헤더에서 배속(×1~×300)과 일시정지를 바꿀 수 있습니다.
- **자동 작업자**를 끄면 알람에 직접 대응해야 합니다. STOP 상태에서 유지보수 조치를 한 뒤 RESET, START 순서로 재가동합니다.
- 실시간 실행 로그도 `logs/<run_id>/`에 1초마다 기록됩니다.

**엔지니어 콘솔** 탭에서는 다음을 할 수 있습니다. 고장 정답이 보이는 화면이므로, AI 분석 결과는 이 화면을 보기 전에 기록해 두세요.

- 시나리오를 골라 새 실행 시작
- 고장 종류와 파라미터를 정해 지금 또는 N분 뒤에 주입
- 고장 상태(예약됨, 진행 중, 해결됨), 진행률, 해결 조치 확인
- 센서에 보이지 않는 실제 물리 상태 확인 (노즐 개방률, 누설률, 실제 온도와 HMI 표시 온도 비교 등)
- 정답 파일(`ground_truth/<run_id>/faults.json`)은 실행 중에도 1초마다 갱신됩니다.

| API | 설명 |
|---|---|
| `GET /api/state`, `WS /ws` | 장비 상태 (WebSocket은 0.1초마다 전송) |
| `POST /api/machine/{start\|stop\|reset}` | 운전 명령 |
| `POST /api/maintenance` `{action}` | 유지보수 조치 (정지 상태에서만) |
| `POST /api/operator` `{auto}` | 자동 작업자 켜기/끄기 |
| `POST /api/sim` `{speed, paused}` | 배속, 일시정지 |
| `POST /api/runs` `{scenario}` | 새 실행 시작 (시나리오 생략 시 고장 없는 live 실행) |
| `POST /api/faults` `{type, params, delay_min}` | 고장 주입 (엔지니어 콘솔용) |
| `GET /api/meta` | 시나리오, 고장 종류와 기본 파라미터, 조치 목록, 알람 코드 |

## 장비 구성

```
[LOADER] → [VISION] → [DISPENSER] → [INSPECTION] → [UNLOADER]
 흡착 픽업    마크 정렬    비드 도포       비드 폭 검사      OK 트레이 / NG 슈트
                           + 주기적 weight check
```

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
| `logs/<run_id>/machine_info.json` | 장비 ID, 레시피, 알람 코드표 | 분석 입력 |
| `ground_truth/<run_id>/faults.json` | 주입한 고장, 발생/해결 시각, 해결 조치 | **평가 전용** |
| `ground_truth/<run_id>/hidden_state.csv` | 10초 주기 실제 물리 상태 (노즐 개방률, 누설률, 실제 온도 등) | **평가 전용** |

`run_id`는 시나리오 이름을 드러내지 않도록 만들어집니다. 로그 안에도 고장 정보가 없습니다(테스트로 확인).

## 고장 시나리오

| 고장 | 숨겨진 원인 | 로그에 나타나는 징후 | 해결 조치 |
|---|---|---|---|
| `nozzle_clog` | 노즐 내부 경화로 유로가 좁아짐 | weight check 값 하락 → E3005, 비드 폭 감소 | 노즐 청소 |
| `vacuum_leak` | 흡착 패드 마모로 진공 누설 | 픽업 진공값이 임계치로 접근 → 재시도 경고 → E1001 반복 | 패드 교체 |
| `temp_sensor_drift` | 온도 센서가 높게 읽어서 실제로는 덜 가열됨 | **표시 온도는 정상**, weight check 값 하락 → E3005가 노즐 청소나 시린지 교체로는 안 고쳐짐 | 엔지니어 교정 |

정상 가동 중에도 매거진 소진(E1002), 트레이 가득 참(E5001), 시린지 교체(E3003), 간헐적인 비전 인식 실패(E2001) 같은 일상적인 알람이 섞여 나옵니다.

새 고장은 `faults/library.py`에 `Fault`를 상속한 클래스를 추가하고 `FAULT_TYPES`에 등록하면 됩니다.

## 폴더 구조

```
config/          장비 설정, 시나리오
simulator/       시뮬레이터 (clock, physics, sensors, stations, machine, operator, simulation)
faults/          고장 엔진과 고장 라이브러리
server/          FastAPI 실시간 서버 (시뮬레이터 구동, REST + WebSocket)
web/             React + Vite 화면 (HMI, 엔지니어 콘솔, 이후 3D 뷰어)
analysis/        AI 로그 분석 (직접 구현)
eval/            분석 결과 평가 (직접 구현)
docs/references/ 참고 매뉴얼 보관 (git 제외)
tests/
```

## 다음 단계

1. 실제 디스펜싱 경험과 매뉴얼을 바탕으로 파라미터, 알람, 고장 시나리오 보강
2. HMI 센서 트렌드 그래프
3. 3D 뷰어 (Three.js / React Three Fiber)
