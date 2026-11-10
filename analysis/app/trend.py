"""분석 탭 사건 그래프. 토출 중 압력·진공을 몇 초씩 묶은 중앙값과, 경비원이 보는 평소 범위.
규칙·경비원과 같은 샘플(운전 중이고 밸브가 열린 순간)만 써서, 그래프와 판단이 같은 값을 본다."""
import bisect
import math
import statistics
from datetime import timedelta

from .anomaly import Z_MAX

BEFORE = timedelta(minutes=60)   # 첫 경보 앞: 고장이 서서히 커지는 모습이 보이도록
AFTER = timedelta(minutes=20)    # 마지막 경보 뒤: 조치 뒤 돌아오는지 보이도록
MAX_SPAN = timedelta(hours=8)
MAX_POINTS = 240
MIN_STEP_S = 10

SERIES = {"pressure": ("disp_pressure_kpa", "disp_pressure_kpa"), "vacuum": ("fixture_vac_kpa", "vacuum_kpa")}


def window(started_at, last_at):
    """사건 하나를 볼 구간. 너무 긴 사건은 첫 경보 쪽을 남긴다."""
    start, end = started_at - BEFORE, last_at + AFTER
    return start, min(end, start + MAX_SPAN)


def step_seconds(start, end):
    return max(MIN_STEP_S, math.ceil((end - start).total_seconds() / MAX_POINTS))


def _band(profile, recipe, key):
    normal = (profile or {}).get(recipe, {}).get(key)
    if not normal:
        return None
    return [round(normal["mean"] - Z_MAX * normal["std"], 2), round(normal["mean"] + Z_MAX * normal["std"], 2)]


def build(samples, parts, start, end, profile):
    """samples: sensor_trend 행 (ts 순서), parts: production 행 (start_time, recipe; 순서).
    점마다 묶음 가운데 시각, 압력·진공 중앙값, 그때 레시피와 평소 범위(평균 ± 3σ)."""
    step = step_seconds(start, end)
    groups = {}
    for s in samples:
        if not (start <= s["ts"] < end) or s["mode"] != "RUNNING" or s["disp_valve_open"] != 1:
            continue
        groups.setdefault(int((s["ts"] - start).total_seconds() // step), []).append(s)

    part_ts = [p["start_time"] for p in parts]
    points = []
    for i in sorted(groups):
        rows = groups[i]
        t = start + timedelta(seconds=i * step + step / 2)
        j = bisect.bisect_right(part_ts, t) - 1
        recipe = parts[j]["recipe"] if j >= 0 else None
        point = {"t": t.isoformat(timespec="seconds"), "recipe": recipe}
        for name, (column, key) in SERIES.items():
            values = [r[column] for r in rows if r[column] is not None]
            point[name] = round(statistics.median(values), 2) if values else None
            point[f"{name}_band"] = _band(profile, recipe, key)
        points.append(point)
    return {"start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds"),
            "step_s": step, "points": points}
