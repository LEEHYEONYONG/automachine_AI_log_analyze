# 이상 탐지 (2주차). 규칙(rules.py)이 "아는 고장의 흔적"을 찾는다면, 여기는 "평소와 다르다"만 본다.
# 평소 모습은 train_anomaly.py가 dev 정상 구간에서 배워 anomaly_profile.json에 저장한다. 숫자는 eval/explore/ 참고
import bisect
import json
import statistics
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path

PROFILE_FILE = Path(__file__).with_name("anomaly_profile.json")

# 공장이라면 어차피 보는 기본 값 5개만 쓴다. 사유별 불량 개수(VOID·STRINGING)는 고장을 보고 고른 값이라 뺐다:
# 빼도 dev 점수가 같았고(26/31), 그래야 "처음 보는 고장도 잡는다"고 말할 수 있다 → 10/30 실험 기록
MEASURES = ["bead_width_mm", "bead_offset_mm", "disp_pressure_kpa"]
COUNTS = ["ng_10min"]   # 사유 상관없이 최근 10분 불량 개수
FEATURES = MEASURES + ["vacuum_kpa"] + COUNTS

WINDOW = 10                         # 측정값은 레시피별 최근 10개 제품의 중앙값 (한 개 튀는 건 무시)
VAC_WINDOW = 20                     # 진공은 토출 중 샘플 20개의 중앙값 (규칙 2와 같음)
NG_LOOK = timedelta(minutes=10)     # 불량은 최근 10분 개수
Z_MAX = 3.0                         # |z|가 이보다 크면 평소와 다름
Z_STREAK = 10                       # 이만큼(약 4분) 연속이어야 울림. 값 여러 개 x 제품 900개를 검사하니 한 번 넘는 건 우연이 섞임


def features(parts, sensors):
    """제품마다 값 5개를 만든다. (시각, 레시피, {값 이름: 값}) 를 차례로 내보냄.
    parts: production 행 (start_time 순서), sensors: sensor_trend 행 (ts 순서)."""
    vac = [(s["ts"], s["fixture_vac_kpa"]) for s in sensors
           if s["mode"] == "RUNNING" and s["disp_valve_open"] == 1]
    vac_ts = [v[0] for v in vac]
    windows = defaultdict(lambda: {k: deque(maxlen=WINDOW) for k in MEASURES})
    ng = deque()   # 최근 10분 불량 시각

    for p in parts:
        ts = p["start_time"]
        w = windows[p["recipe"]]
        for k in MEASURES:
            if p[k] is not None:
                w[k].append(p[k])
        if p["ng_reason"]:
            ng.append(ts)
        while ng and ng[0] < ts - NG_LOOK:
            ng.popleft()

        i = bisect.bisect_right(vac_ts, ts)
        if i < VAC_WINDOW or any(len(w[k]) < WINDOW for k in MEASURES):
            continue
        values = {k: statistics.median(w[k]) for k in MEASURES}
        values["vacuum_kpa"] = statistics.median(v[1] for v in vac[i - VAC_WINDOW:i])
        values["ng_10min"] = len(ng)
        yield ts, p["recipe"], values


def learn(normal_rows):
    """정상 구간의 (레시피, 값들) 목록에서 평소 모습을 배운다.
    측정값·진공은 평균과 표준편차, 불량 개수는 평소 최대치 (개수는 대부분 0이라 z-score가 맞지 않음)."""
    seen = defaultdict(lambda: defaultdict(list))
    for recipe, values in normal_rows:
        for k in FEATURES:
            seen[recipe][k].append(values[k])
    profile = {}
    for recipe, cols in seen.items():
        profile[recipe] = {k: {"max": max(v)} if k in COUNTS
                           else {"mean": statistics.mean(v), "std": statistics.pstdev(v)}
                           for k, v in cols.items()}
        profile[recipe]["samples"] = len(cols[FEATURES[0]])
    return profile


def load_profile():
    return json.loads(PROFILE_FILE.read_text(encoding="utf-8")) if PROFILE_FILE.exists() else {}


def detect_anomaly(run_id, parts, sensors, profile):
    """평소 모습에서 벗어나면 anomaly. 어떤 고장인지는 모르고, 어느 값이 얼마나 벗어났는지만 남긴다.
    배운 적 없는 레시피(제품)는 평소 모습을 몰라서 건너뛴다 → 경비원의 약점, 실험 기록 참고."""
    results = []
    streak = defaultdict(int)

    for ts, recipe, values in features(parts, sensors):
        normal = profile.get(recipe)
        if normal is None:
            continue
        for k in FEATURES:
            if k in COUNTS:
                hit = values[k] > normal[k]["max"]
                need = 1                 # 10분 개수라 한 번 넘으면 이미 "계속" 넘은 것
                evidence = {"count_10min": values[k], "normal_max": normal[k]["max"]}
            else:
                mean, std = normal[k]["mean"], normal[k]["std"]
                z = (values[k] - mean) / std if std else 0.0
                hit = abs(z) > Z_MAX
                need = Z_STREAK
                evidence = {"value": values[k], "z": round(z, 1), "normal_mean": mean, "normal_std": std}
            streak[k] = streak[k] + 1 if hit else 0
            if streak[k] == need:
                results.append({
                    "run_id": run_id,
                    "fault_type": "anomaly",
                    "detected_at": ts,
                    "evidence": {"feature": k, "recipe": recipe, **evidence},
                })

    return results
