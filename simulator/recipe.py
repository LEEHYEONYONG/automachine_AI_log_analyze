"""Recipe parameter definitions: what the HMI shows, and the limits an edit must respect."""

RECIPE_SPEC: dict[str, dict] = {
    "dispense_pressure_kpa": {"label": "토출 압력", "unit": "kPa", "min": 100.0, "max": 400.0, "step": 1.0},
    "dispense_time_s": {"label": "토출 시간", "unit": "s", "min": 0.5, "max": 5.0, "step": 0.01},
    "retract_delay_s": {"label": "토출 후 대기 (dwell)", "unit": "s", "min": 0.0, "max": 2.0, "step": 0.05},
    "syringe_temp_c": {"label": "시린지 온도", "unit": "°C", "min": 20.0, "max": 50.0, "step": 0.1},
    "nozzle_height_mm": {"label": "도포 갭 (니들 높이)", "unit": "mm", "min": 0.05, "max": 0.5, "step": 0.01},
    "target_bead_weight_mg": {"label": "목표 토출량", "unit": "mg", "min": 1.0, "max": 30.0, "step": 0.1},
    "weight_tolerance_pct": {"label": "토출량 허용 오차", "unit": "%", "min": 1.0, "max": 30.0, "step": 0.5},
    "nominal_bead_width_mm": {"label": "기준 비드 폭", "unit": "mm", "min": 0.2, "max": 2.0, "step": 0.01},
    "bead_width_spec_mm": {"label": "비드 폭 합격 범위 (하한, 상한)", "unit": "mm", "min": 0.1, "max": 3.0, "step": 0.01},
}


def validate(values: dict) -> list[str]:
    """Problems with an edited recipe, in Korean for the HMI (empty when it is valid)."""
    problems = []
    for key, value in values.items():
        spec = RECIPE_SPEC.get(key)
        if spec is None:
            problems.append(f"알 수 없는 항목: {key}")
            continue
        numbers = value if isinstance(value, list) else [value]
        if key == "bead_width_spec_mm" and (len(numbers) != 2 or numbers[0] >= numbers[1]):
            problems.append(f"{spec['label']}: 하한이 상한보다 작은 두 값이어야 합니다")
            continue
        for n in numbers:
            if not isinstance(n, (int, float)) or not spec["min"] <= n <= spec["max"]:
                problems.append(f"{spec['label']}: {spec['min']:g}~{spec['max']:g} {spec['unit']} 범위여야 합니다 (입력 {n})")
    return problems
