# eval/explore/

규칙을 정하기 전에 **dev 런만** 관찰하고, 규칙 후보를 dev 런 전체에 돌려 본 스크립트입니다.
분석 코드(`analysis/`)가 아니라 실험용입니다. 결과와 판단 과정은 Notion "AI 분석 실험 기록"에 있습니다.

- 저장소 루트 어디서든 `bash eval/explore/<파일>`로 실행합니다 (db 컨테이너가 떠 있어야 함).
- `ground_truth/`를 읽으므로 analysis 컨테이너가 아니라 WSL에서 실행합니다.
- **test 런은 열어 보지 않습니다** (`eval/README.md` 6번).

| 파일 | 하는 일 |
|---|---|
| `split_map.sh` | `runs.csv`의 각 줄(scenario, seed)이 어느 run_id인지, dev/test인지 표로 출력 |
| `ingest_verify.sh` | 로그 파일 줄 수와 DB 행 수가 런마다 같은지 확인 |
| `obs_air_supply.sh` | 정상 런 vs air_supply_drop 런, 30분 단위 압력·진공·알람 비교 |
| `obs_air_supply_5min.sh` | air_supply_drop 고장 전후 5분 단위 압력·진공 |
| `obs_recipe_b.sh` | realistic_day 오후 오탐 원인: 제품 B(정상 압력 약 220)로 모델 변경 |
| `obs_no_part.sh` | 제품이 없을 때(RUNNING인데 빈 지그) 진공 0 확인 |
| `obs_purge.sh` | 밸브가 열렸는데 진공 0인 순간(허공 토출) 확인 |
| `rule1_air_supply_drop.sh` | **규칙 1** 최종본을 dev 전체에 적용 |
| `obs_vacuum_leak.sh` | vacuum_leak 런, 30분 단위 압력·진공·알람 |
| `obs_vacuum_normal.sh` | 정상 런 진공 범위, vacuum_leak 런이 기준선별로 처음 넘는 시각 |
| `obs_nozzle_clog.sh` | 정상 런 vs nozzle_clog 런, 30분 단위 비드 폭·압력·NG·알람 (production) |
| `obs_syringe_drift.sh` | 알람 코드 뜻, 정상 런에서 주사기 잔량과 함께 폭이 줄어드는지 |
| `obs_width_drop.sh` | 런마다 '50개 중앙값 폭이 30분 전보다 가장 많이 줄어든 양' |
| `rule3_nozzle_clog.sh` | **규칙 3** 최종본을 dev 전체에 적용 |
| `rule2_vacuum_leak.sh` | **규칙 2** 최종본을 dev 전체에 적용 (급락 조건 10분/60분 두 가지 비교) |
| `anomaly_zscore.sh` | **이상 탐지**(z-score) 공정 채점: 런 하나씩 빼고 배워서 검사, 연속 개수별 비교 (2026-10-30) |
| `anomaly_iforest.sh` | 비교 실험: Isolation Forest, 정답지 없이(A) vs 정상만(B). z-score보다 못함 |
| `anomaly_iforest_mix.sh` | 비교 실험: Isolation Forest를 고장 비율 0~22%로 섞어 배움. 고장이 흔하면 약한 고장을 놓침 |

## 규칙 요약 (2026-10-27, dev 22런 기준)

공통: `mode='RUNNING'`이고 `disp_valve_open=1`(제품을 잡고 토출 중)인 샘플만 본다.

| 규칙 | 조건 | dev 결과 |
|---|---|---|
| 1 air_supply_drop | 압력 < 230 **그리고** 진공 > -75 인 샘플이 20개 연속 | 4/4 탐지, 오탐 0, 지연 4~5분 |
| 2 vacuum_leak | 최근 20샘플 진공 중앙값 > -80 **그리고** 압력 중앙값 ≥ 238. 단 최근 60분 안에 진공이 10분 사이 5 이상 급락했으면 무시 | 2/2 탐지, 오탐 0, 지연 약 35분 |
| 3 nozzle_clog | (production, 제품별) 최근 50개 폭 중앙값이 30분 전보다 0.015 이상 감소. 단 최근 60분 안에 최근 10개 압력 중앙값 < 238이 있었으면 무시 | 2/2 탐지, 지연 약 45분. 오탐 3 (temp_sensor_drift 2, needle_tip_buildup 1: 폭만으로는 구분 불가, 받아들임) |
