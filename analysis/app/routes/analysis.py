import json

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..database import get_db
from .. import anomaly, rules

router = APIRouter(
    prefix="/api/analysis",
    tags=["Analysis"]
)


@router.post("/runs/{run_id}")
def analyze_run(run_id: str, method: Literal["rule", "anomaly"] = "rule", db: Session = Depends(get_db)):
    """런 하나를 분석해 고장 후보를 찾고 analysis_results에 저장한다.
    method=rule은 규칙 7개(고장 이름까지), method=anomaly는 이상 탐지(평소와 다른 값만).
    같은 런을 같은 방법으로 다시 분석하면 이전 결과는 지우고 새로 쓴다."""
    run = db.execute(text("SELECT machine_info->'recipes' AS recipes FROM runs WHERE run_id = :r"),
                     {"r": run_id}).first()
    if run is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    sensors = db.execute(text("""
        SELECT ts, mode, disp_valve_open, disp_pressure_kpa, fixture_vac_kpa
        FROM sensor_trend WHERE run_id = :r ORDER BY ts
    """), {"r": run_id}).mappings().all()
    parts = db.execute(text("""
        SELECT start_time, recipe, bead_width_mm, bead_offset_mm, disp_pressure_kpa, ng_reason
        FROM production WHERE run_id = :r ORDER BY start_time
    """), {"r": run_id}).mappings().all()
    recipe_changes = db.execute(text("""
        SELECT ts, attrs FROM events
        WHERE run_id = :r AND unit = 'HMI' AND message LIKE 'Recipe parameter changed%' ORDER BY ts
    """), {"r": run_id}).mappings().all()

    if method == "anomaly":
        profile = anomaly.load_profile()
        if not profile:
            raise HTTPException(status_code=503, detail="평소 모습이 아직 없음: app.train_anomaly를 먼저 실행")
        candidates = anomaly.detect_anomaly(run_id, parts, sensors, profile)
    else:
        candidates = (rules.detect_air_supply_drop(run_id, sensors)
                      + rules.detect_vacuum_leak(run_id, sensors)
                      + rules.detect_nozzle_clog(run_id, parts)
                      + rules.detect_recipe_error(run_id, recipe_changes, run.recipes or {})
                      + rules.detect_air_bubble(run_id, parts)
                      + rules.detect_needle_offset(run_id, parts)
                      + rules.detect_needle_tip_buildup(run_id, parts, recipe_changes, run.recipes or {}))
    candidates.sort(key=lambda c: c["detected_at"])

    db.execute(text("DELETE FROM analysis_results WHERE run_id = :r AND method = :m"),
               {"r": run_id, "m": method})
    for c in candidates:
        db.execute(text("""
            INSERT INTO analysis_results (run_id, method, predicted_cause, detected_at, evidence)
            VALUES (:r, :m, :cause, :at, CAST(:evidence AS jsonb))
        """), {"r": run_id, "m": method, "cause": c["fault_type"],
               "at": c["detected_at"], "evidence": json.dumps(c["evidence"])})
    db.commit()

    return {"run_id": run_id, "method": method, "count": len(candidates), "candidates": candidates}
