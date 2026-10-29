# 진단 도구 (3주차 반장(LLM 에이전트)이 쓸 예정). rules.py가 "미리 알아채기"라면, 여기는 "이미 난 고장의 원인 좁히기".
# 탐지 점수(eval/score.py)에는 들어가지 않는다 → 10/29 결정, 실험 기록 참고
import statistics

RECOVER_BEFORE = 50      # 청소 전 마지막 50개 제품의 폭 중앙값과
RECOVER_AFTER = 30       # 청소 후 첫 30개 제품의 폭 중앙값을 비교
RECOVER_MIN = 0.015      # dev: 진짜 막힘이면 +0.026~0.040 회복, 온도 센서면 -0.007~+0.008


def width_recovered_after_clean(parts, clean_at):
    """노즐 청소 뒤 비드 폭이 돌아왔는지. 폭이 줄어 막힘처럼 보였을 때 막힘 vs 온도 센서를 가른다.
    (폭만으로는 둘 다 접착제가 덜 나와서 구분이 안 되고, 압력 차이는 센서 잡음보다 작아서 못 씀)
    parts: 한 런의 production 행 (start_time 순서), clean_at: 노즐 청소 완료 시각.
    청소 후 제품이 아직 30개가 안 되면 None."""
    parts = [p for p in parts if p["bead_width_mm"] is not None]
    before = [p for p in parts if p["start_time"] < clean_at][-RECOVER_BEFORE:]
    if not before:
        return None
    recipe = before[-1]["recipe"]
    before = [p["bead_width_mm"] for p in before if p["recipe"] == recipe]
    after = [p for p in parts if p["start_time"] > clean_at and p["recipe"] == recipe][:RECOVER_AFTER]
    if len(after) < RECOVER_AFTER:
        return None

    width_before = statistics.median(before)
    width_after = statistics.median(p["bead_width_mm"] for p in after)
    recovered = width_after - width_before >= RECOVER_MIN
    return {
        "recipe": recipe,
        "width_before_clean_mm": width_before,
        "width_after_clean_mm": width_after,
        "recovered": recovered,
        "suspect": "nozzle_clog" if recovered else "temp_sensor_drift",
        "checked_at": after[-1]["start_time"],
    }
