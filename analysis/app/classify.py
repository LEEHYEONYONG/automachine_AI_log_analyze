# 원인 분류 (3주차). 경비원(anomaly.py)이 울린 순간의 모습을 보고 고장 이름을 고른다.
# 규칙은 고장마다 사람이 조건을 썼고, 여기는 dev 런의 "울린 순간 → 정답 고장" 예시에서 결정 트리가 조건을 배운다.
# 학습은 train_classifier.py, 결과 파일은 classifier.json. 예시가 수십 개뿐이라 트리를 작게 유지한다.
import json
import statistics
from datetime import timedelta
from pathlib import Path

from sqlalchemy import text

from .anomaly import detect_anomaly, features
from .rules import RECIPE_TOLERANCE

MODEL_FILE = Path(__file__).with_name("classifier.json")

NO_FAULT = "no_fault"       # 정답 고장이 없는 순간에 울린 경우. 이렇게 분류되면 후보로 내지 않는다
UNKNOWN = "unknown"         # 트리가 확신하지 못한 경우. 처음 보는 고장일 수도 있다
MIN_CONFIDENCE = 0.6        # 도달한 잎에서 가장 많은 종류의 비율이 이보다 낮으면 unknown

NG_LOOK = timedelta(minutes=10)
TEMP_WINDOW = 10            # 표시 온도는 최근 10개 제품의 중앙값
RECENT = timedelta(minutes=30)
NG_FEATURES = {"BEAD_VOID": "ng_void", "STRINGING": "ng_stringing", "WIDTH_LOW": "ng_width_low",
               "BEAD_OFFSET": "ng_offset"}

FEATURE_NAMES = ["z_width", "z_offset", "z_pressure", "z_vacuum", "temp_c", *NG_FEATURES.values(),
                 "pressure_setting_wrong", "retract_setting_wrong", "after_clean", "after_syringe"]


def load_context(db, run_id):
    """분류와 반장이 함께 쓰는 런 자료. 진공은 토출 중 값만 쓰므로 그 줄만 읽어 메모리를 아낀다."""
    run = db.execute(text("SELECT machine_info->'recipes' AS recipes FROM runs WHERE run_id = :r"),
                     {"r": run_id}).first()
    return {
        "run_id": run_id,
        "recipes": (run.recipes or {}) if run else {},
        "parts": db.execute(text("""
            SELECT start_time, recipe, lot_id, bead_width_mm, bead_offset_mm, disp_pressure_kpa, disp_temp_c,
                   fixture_vac_kpa, ng_reason
            FROM production WHERE run_id = :r ORDER BY start_time
        """), {"r": run_id}).mappings().all(),
        "sensors": db.execute(text("""
            SELECT ts, mode, disp_valve_open, fixture_vac_kpa FROM sensor_trend
            WHERE run_id = :r AND mode = 'RUNNING' AND disp_valve_open = 1 ORDER BY ts
        """), {"r": run_id}).mappings().all(),
        "changes": db.execute(text("""
            SELECT ts, attrs FROM events
            WHERE run_id = :r AND unit = 'HMI' AND message LIKE 'Recipe parameter changed%' ORDER BY ts
        """), {"r": run_id}).mappings().all(),
        "machine_events": db.execute(text("""
            SELECT ts, message, attrs FROM events
            WHERE run_id = :r AND ((unit = 'HMI' AND message LIKE 'Setting changed%')
                OR (unit = 'MACHINE' AND (message LIKE 'Run mode change%' OR message LIKE 'Dummy run done%')))
            ORDER BY ts
        """), {"r": run_id}).mappings().all(),
        "maintenance": db.execute(text("""
            SELECT ts, attrs->>'action' AS action FROM events
            WHERE run_id = :r AND unit = 'MAINT' AND message LIKE 'Maintenance done%' ORDER BY ts
        """), {"r": run_id}).mappings().all(),
    }


def _setting_wrong(ctx, ts, param):
    """ts 시점에 그 설정값이 표준에서 10% 넘게 벗어나 있었는가. 마지막 변경 기록으로 본다."""
    wrong = 0
    for c in ctx["changes"]:
        a = c["attrs"]
        standard = ctx["recipes"].get(a["recipe"], {}).get(param)
        if c["ts"] <= ts and a["param"] == param and standard:
            wrong = int(abs(float(a["new"]) - standard) / standard > RECIPE_TOLERANCE)
    return wrong


def _recent_action(ctx, ts, action):
    return int(any(ts - RECENT <= m["ts"] <= ts and m["action"] == action for m in ctx["maintenance"]))


def snapshot(ctx, ts, recipe, values, normal):
    """경비원이 울린 순간의 모습. ts 뒤의 자료는 쓰지 않는다 (그때 알 수 없던 것으로 맞히면 반칙)."""
    def z(key, field):
        std = normal[key]["std"]
        return (values[field] - normal[key]["mean"]) / std if std else 0.0

    past = [p for p in ctx["parts"] if p["start_time"] <= ts]
    recent_ng = [p["ng_reason"] for p in past if p["start_time"] >= ts - NG_LOOK and p["ng_reason"]]
    temps = [p["disp_temp_c"] for p in past if p["disp_temp_c"] is not None][-TEMP_WINDOW:]
    row = {
        "z_width": z("bead_width_mm", "bead_width_mm"),
        "z_offset": z("bead_offset_mm", "bead_offset_mm"),
        "z_pressure": z("disp_pressure_kpa", "disp_pressure_kpa"),
        "z_vacuum": z("vacuum_kpa", "vacuum_kpa"),
        "temp_c": statistics.median(temps) if temps else 0.0,
        "pressure_setting_wrong": _setting_wrong(ctx, ts, "dispense_pressure_kpa"),
        "retract_setting_wrong": _setting_wrong(ctx, ts, "retract_delay_s"),
        "after_clean": _recent_action(ctx, ts, "nozzle_clean"),
        "after_syringe": _recent_action(ctx, ts, "replace_syringe"),
    }
    for reason, name in NG_FEATURES.items():
        row[name] = recent_ng.count(reason)
    return row


def alert_snapshots(ctx, profile):
    """경비원이 울린 순간마다 (경비원 후보, 그 순간의 모습)을 돌려준다."""
    alerts = detect_anomaly(ctx["run_id"], ctx["parts"], ctx["sensors"], profile)
    if not alerts:
        return []
    moments = {ts: (recipe, values) for ts, recipe, values in features(ctx["parts"], ctx["sensors"])}
    pairs = []
    for alert in sorted(alerts, key=lambda a: a["detected_at"]):
        recipe, values = moments[alert["detected_at"]]
        pairs.append((alert, snapshot(ctx, alert["detected_at"], recipe, values, profile[recipe])))
    return pairs


def to_json(tree, classes):
    """sklearn 트리를 숫자 표로 옮긴다. 파일을 읽어 볼 수 있고, API가 sklearn 없이 답한다."""
    t = tree.tree_
    return {
        "features": FEATURE_NAMES,
        "classes": list(classes),
        "left": t.children_left.tolist(),
        "right": t.children_right.tolist(),
        "feature": t.feature.tolist(),
        "threshold": t.threshold.tolist(),
        "value": [v[0].tolist() for v in t.value],
    }


def predict(model, row):
    """(고장 이름, 확신도). 트리를 뿌리부터 따라 내려가 도달한 잎의 비율을 본다."""
    node = 0
    while model["left"][node] != -1:
        go_left = row[model["features"][model["feature"][node]]] <= model["threshold"][node]
        node = model["left"][node] if go_left else model["right"][node]
    counts = model["value"][node]
    best = max(range(len(counts)), key=lambda i: counts[i])
    return model["classes"][best], counts[best] / sum(counts)


def classify_run(ctx, profile, model):
    """경비원 후보에 이름을 붙인다. 고장이 아니라고 판단한 후보는 빼고, 확신이 낮으면 unknown으로 남긴다."""
    results = []
    for alert, row in alert_snapshots(ctx, profile):
        name, confidence = predict(model, row)
        if name == NO_FAULT:
            continue
        results.append({
            "run_id": ctx["run_id"],
            "fault_type": name if confidence >= MIN_CONFIDENCE else UNKNOWN,
            "detected_at": alert["detected_at"],
            "confidence": round(confidence, 2),
            "evidence": {**alert["evidence"], "best_guess": name, "snapshot": {k: round(v, 2) for k, v in row.items()}},
        })
    return results


def load_model():
    return json.loads(MODEL_FILE.read_text(encoding="utf-8")) if MODEL_FILE.exists() else None
