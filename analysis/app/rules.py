# 규칙 기반 탐지 (1주차). 숫자는 dev 관찰로 정한 값 → eval/explore/ 참고
import statistics
from collections import deque
from datetime import timedelta

# 규칙 1: air_supply_drop
AIR_PRESSURE_MAX = 230   # 이보다 낮으면 압력 이상
AIR_VACUUM_MIN = -75     # 이보다 높으면(0에 가까우면) 진공 이상
AIR_CONSECUTIVE = 20     # 이만큼 연속이어야 고장으로 판단

def detect_air_supply_drop(run_id, samples):
    """samples: 한 런의 sensor_trend 행 목록 (ts 순서)"""
    results = []
    count = 0

    for s in samples:
        # ① 토출 중인 샘플만 본다 (나머지는 건너뜀)
        if s["mode"] != "RUNNING" or s["disp_valve_open"] != 1:
            continue

        # ② 이상한 샘플이면 +1, 정상이면 0으로
        bad = s["disp_pressure_kpa"] < AIR_PRESSURE_MAX and s["fixture_vac_kpa"] > AIR_VACUUM_MIN
        if bad:
            count += 1
        else:
            count = 0

        # ③ 딱 20번째에서 한 번만 기록
        if count == AIR_CONSECUTIVE:
            results.append({
                "run_id": run_id,
                "fault_type": "air_supply_drop",
                "detected_at": s["ts"],
                "evidence": {
                    "pressure_kpa": s["disp_pressure_kpa"],
                    "vacuum_kpa": s["fixture_vac_kpa"],
                    "consecutive": AIR_CONSECUTIVE,
                },
            })
    return results


# 규칙 2: vacuum_leak
LEAK_WINDOW = 20                        # 최근 몇 개 샘플의 중앙값을 볼지
LEAK_VACUUM_MIN = -80                   # 진공 중앙값이 이보다 높으면(약하면) 이상
LEAK_PRESSURE_MIN = 238                 # 압력 중앙값이 이 이상이면 압력은 정상 → 공기 부족이 아님
LEAK_DROP = 5                           # 진공 중앙값이 이만큼 이상 갑자기 약해지면 "급락"
LEAK_DROP_LOOK = timedelta(minutes=10)  # 급락은 10분 전 값과 비교
LEAK_MEMORY = timedelta(minutes=60)     # 급락이 있었으면 60분 동안은 무시 (공기 부족의 시작·회복 순간)


def detect_vacuum_leak(run_id, samples):
    """진공이 천천히 약해지는데 압력은 정상이면 vacuum_leak.
    진공 샘은 몇 시간에 걸쳐 서서히 약해지므로, 갑자기 약해진 경우(공기 부족)는 제외한다."""
    results = []
    window = []            # 최근 20개 샘플
    past = deque()         # (시각, 진공 중앙값) 기록. 맨 앞이 "10분 전" 값이 되도록 유지
    last_sudden = None     # 마지막으로 급락이 보인 시각
    on = False             # 이미 외쳤는지 (켜지는 순간에만 기록)

    for s in samples:
        # 토출 중인 샘플만 본다
        if s["mode"] != "RUNNING" or s["disp_valve_open"] != 1:
            continue

        # 최근 20개만 남기기
        window.append(s)
        if len(window) > LEAK_WINDOW:
            window.pop(0)
        if len(window) < LEAK_WINDOW:
            continue

        ts = s["ts"]
        vac = statistics.median(x["fixture_vac_kpa"] for x in window)
        pres = statistics.median(x["disp_pressure_kpa"] for x in window)

        # 10분 전 진공 중앙값과 비교해서 급락이면 시각을 기억
        past.append((ts, vac))
        while len(past) >= 2 and past[1][0] <= ts - LEAK_DROP_LOOK:
            past.popleft()
        if past[0][0] <= ts - LEAK_DROP_LOOK and vac - past[0][1] >= LEAK_DROP:
            last_sudden = ts

        recent_sudden = last_sudden is not None and ts - last_sudden <= LEAK_MEMORY
        hit = vac > LEAK_VACUUM_MIN and pres >= LEAK_PRESSURE_MIN and not recent_sudden

        if hit and not on:
            results.append({
                "run_id": run_id,
                "fault_type": "vacuum_leak",
                "detected_at": ts,
                "evidence": {
                    "vacuum_median_kpa": vac,
                    "pressure_median_kpa": pres,
                    "window": LEAK_WINDOW,
                },
            })
        on = hit

    return results


# 규칙 3: nozzle_clog (production 표: 제품 1개당 1줄)
CLOG_WINDOW = 50                        # 최근 몇 개 제품의 폭 중앙값을 볼지
CLOG_DROP = 0.015                       # 폭 중앙값이 이만큼(mm) 이상 줄면 이상
CLOG_LOOK = timedelta(minutes=30)       # 30분 전 폭 중앙값과 비교
CLOG_PRESSURE_WINDOW = 10               # 압력은 최근 10개만 본다 (빨리 반응하도록)
CLOG_PRESSURE_MIN = 238                 # 압력 중앙값이 이보다 낮으면 압력 문제
CLOG_MEMORY = timedelta(minutes=60)     # 압력 문제가 있었으면 60분 동안은 무시 (공기 부족의 시작·회복 순간)


def detect_nozzle_clog(run_id, parts):
    """parts: 한 런의 production 행 목록 (start_time 순서).
    정상 폭은 제품(recipe)마다 다르므로 제품별로 따로 본다."""
    by_recipe = {}
    for p in parts:
        if p["bead_width_mm"] is None:
            continue
        by_recipe.setdefault(p["recipe"], []).append(p)

    results = []
    for recipe_parts in by_recipe.values():
        results += _detect_nozzle_clog_one_recipe(run_id, recipe_parts)
    results.sort(key=lambda r: r["detected_at"])
    return results


def _detect_nozzle_clog_one_recipe(run_id, parts):
    """같은 제품끼리만: 폭 중앙값이 30분 전보다 확 줄었는데 압력 문제는 없었으면 nozzle_clog.
    주사기가 비면서 폭이 천천히 줄어드는 건 정상이라 30분 사이의 변화만 본다."""
    results = []
    window = []            # 최근 50개 제품
    past = deque()         # (시각, 폭 중앙값) 기록. 맨 앞이 "30분 전" 값이 되도록 유지
    last_low = None        # 마지막으로 압력이 낮았던 시각
    on = False

    for p in parts:
        window.append(p)
        if len(window) > CLOG_WINDOW:
            window.pop(0)
        if len(window) < CLOG_WINDOW:
            continue

        ts = p["start_time"]
        width = statistics.median(x["bead_width_mm"] for x in window)
        pres = statistics.median(x["disp_pressure_kpa"] for x in window[-CLOG_PRESSURE_WINDOW:])
        if pres < CLOG_PRESSURE_MIN:
            last_low = ts

        past.append((ts, width))
        while len(past) >= 2 and past[1][0] <= ts - CLOG_LOOK:
            past.popleft()
        before = past[0][1] if past[0][0] <= ts - CLOG_LOOK else None

        recent_low = last_low is not None and ts - last_low <= CLOG_MEMORY
        hit = before is not None and before - width >= CLOG_DROP and not recent_low

        if hit and not on:
            results.append({
                "run_id": run_id,
                "fault_type": "nozzle_clog",
                "detected_at": ts,
                "evidence": {
                    "recipe": p["recipe"],
                    "width_median_30min_ago_mm": before,
                    "width_median_mm": width,
                    "pressure_median_kpa": pres,
                },
            })
        on = hit

    return results


# 규칙 4: recipe_pressure_error, recipe_retract_error (event.log의 HMI 설정 변경 기록)
RECIPE_TOLERANCE = 0.10                 # 새 값이 표준값에서 10% 넘게 벗어나면 오입력 (장비 무게 허용 오차와 같은 폭)
RECIPE_PARAM_FAULT = {                  # 어떤 설정이 틀리면 어떤 고장인지
    "dispense_pressure_kpa": "recipe_pressure_error",
    "retract_delay_s": "recipe_retract_error",
}


def detect_recipe_error(run_id, changes, recipes):
    """changes: 한 런의 "Recipe parameter changed" 이벤트 (ts, attrs) 목록 (ts 순서)
    recipes: 런 시작 때의 표준 레시피 (runs.machine_info의 recipes)
    "바뀌었다"가 아니라 "표준값에서 크게 벗어났다"를 본다. 원래대로 되돌리는 변경은 고장이 아니다."""
    results = []
    for c in changes:
        a = c["attrs"]
        fault = RECIPE_PARAM_FAULT.get(a["param"])
        standard = recipes.get(a["recipe"], {}).get(a["param"])
        if fault is None or not standard:
            continue

        deviation = (float(a["new"]) - standard) / standard
        if abs(deviation) > RECIPE_TOLERANCE:
            results.append({
                "run_id": run_id,
                "fault_type": fault,
                "detected_at": c["ts"],
                "evidence": {
                    "recipe": a["recipe"],
                    "param": a["param"],
                    "old": float(a["old"]),
                    "new": float(a["new"]),
                    "standard": standard,
                    "deviation_pct": round(deviation * 100, 1),
                    "by": a.get("by"),
                },
            })
    return results