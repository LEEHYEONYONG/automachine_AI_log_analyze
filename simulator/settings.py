"""Machine settings an engineer can change from the HMI settings screen, with their limits.

Each setting points at a value in config/machine.json. The stations read those values every
cycle, so a change takes effect at once. Changes are logged like recipe edits. What is fixed by
hardware is listed separately and shown read-only.
"""
from __future__ import annotations

# key: (path in machine.json, group, label, unit, min, max, step, level)
SPEC: dict[str, tuple] = {
    "lot_size": (("lot_size",), "production", "로트 크기", "개", 10, 5000, 1, "ENGINEER"),
    "production_target": (("production_target",), "production", "생산 목표 (0이면 끔)", "개", 0, 20000, 1, "ENGINEER"),
    "weight_check_interval": (("dispenser", "weight_check_interval"), "dispenser", "중량 검사 주기", "개", 10, 1000, 1, "MAKER"),
    "vacuum_threshold_kpa": (("dispenser", "vacuum_threshold_kpa"), "dispenser", "진공 판정 기준", "kPa", -85, -30, 1, "MAKER"),
    "max_vacuum_retries": (("dispenser", "max_vacuum_retries"), "dispenser", "진공 재시도", "회", 0, 5, 1, "MAKER"),
    "temp_alarm_band_c": (("dispenser", "temp_alarm_band_c"), "dispenser", "온도 감시 폭 (±)", "°C", 0.5, 10.0, 0.1, "MAKER"),
    "syringe_low_pct": (("dispenser", "syringe_low_pct"), "dispenser", "시린지 잔량 경고", "%", 1, 30, 1, "MAKER"),
    "pot_life_h": (("dispenser", "pot_life_h"), "dispenser", "가사 시간", "h", 1.0, 24.0, 0.5, "MAKER"),
    "vision_score_threshold": (("vision", "score_threshold"), "vision", "정렬 점수 기준", "", 0.3, 0.95, 0.01, "MAKER"),
    "vision_max_offset_mm": (("vision", "max_offset_mm"), "vision", "정렬 허용 위치 차", "mm", 0.05, 0.5, 0.01, "MAKER"),
    "bead_max_offset_mm": (("inspection", "max_bead_offset_mm"), "inspection", "비드 위치 허용", "mm", 0.02, 0.5, 0.01, "MAKER"),
    "max_consecutive_ng": (("inspection", "max_consecutive_ng"), "inspection", "연속 불량 정지 수", "개", 1, 20, 1, "MAKER"),
}
DEFAULTS = {"production_target": 0}   # settings that machine.json does not have

# Fixed by hardware or by the data logger; shown so the engineer knows them, never changed here.
READ_ONLY: dict[str, tuple] = {
    "air_pressure_switch_kpa": (("air_pressure_switch_kpa",), "메인 에어 압력 스위치", "kPa"),
    "ng_buffer_capacity": (("outfeed", "ng_buffer_capacity"), "NG 버퍼 용량", "개"),
    "sensor_sample_s": (("sensor_sample_s",), "센서 기록 주기", "s"),
    "syringe_capacity_ml": (("dispenser", "syringe_capacity_ml"), "시린지 용량", "ml"),
    "material_density_g_per_ml": (("dispenser", "material_density_g_per_ml"), "접착제 밀도", "g/ml"),
}


def get(cfg: dict, key: str):
    path = (SPEC.get(key) or READ_ONLY[key])[0]
    node = cfg
    for part in path[:-1]:
        node = node[part]
    return node.get(path[-1], DEFAULTS.get(key))


def put(cfg: dict, key: str, value) -> None:
    path = SPEC[key][0]
    node = cfg
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value


def coerce(key: str, value):
    """The value as the machine stores it (int when the step is whole), or ValueError with a Korean reason."""
    _, _, label, unit, lo, hi, step, _ = SPEC[key]
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}: 숫자를 넣어 주세요") from None
    if not lo <= number <= hi:
        raise ValueError(f"{label}: {lo:g}~{hi:g} {unit} 범위여야 합니다 (입력 {value})".replace("  ", " "))
    return int(round(number)) if float(step).is_integer() else round(number, 3)


def view(cfg: dict, standard: dict) -> dict:
    """What the settings screen shows: each value next to its standard (the shipped machine.json)."""
    editable = [{
        "key": key, "group": group, "label": label, "unit": unit, "min": lo, "max": hi, "step": step,
        "level": level, "value": get(cfg, key), "standard": get(standard, key),
    } for key, (_, group, label, unit, lo, hi, step, level) in SPEC.items()]
    fixed = [{"key": key, "label": label, "unit": unit, "value": get(cfg, key)}
             for key, (_, label, unit) in READ_ONLY.items()]
    return {"editable": editable, "read_only": fixed}


def current(cfg: dict) -> dict:
    return {key: get(cfg, key) for key in SPEC}
