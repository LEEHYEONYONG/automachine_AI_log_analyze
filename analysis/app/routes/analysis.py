import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..database import get_db
from .. import rules

router = APIRouter(
    prefix="/api/analysis",
    tags=["Analysis"]
)

METHOD = "rule"


@router.post("/runs/{run_id}")
def analyze_run(run_id: str, db: Session = Depends(get_db)):
    """런 하나에 규칙을 돌려 고장 후보를 찾고 analysis_results에 저장한다.
    같은 런을 다시 분석하면 이전 규칙 결과는 지우고 새로 쓴다."""
    if db.execute(text("SELECT 1 FROM runs WHERE run_id = :r"), {"r": run_id}).first() is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    sensors = db.execute(text("""
        SELECT ts, mode, disp_valve_open, disp_pressure_kpa, fixture_vac_kpa
        FROM sensor_trend WHERE run_id = :r ORDER BY ts
    """), {"r": run_id}).mappings().all()
    parts = db.execute(text("""
        SELECT start_time, recipe, bead_width_mm, disp_pressure_kpa
        FROM production WHERE run_id = :r ORDER BY start_time
    """), {"r": run_id}).mappings().all()

    candidates = (rules.detect_air_supply_drop(run_id, sensors)
                  + rules.detect_vacuum_leak(run_id, sensors)
                  + rules.detect_nozzle_clog(run_id, parts))
    candidates.sort(key=lambda c: c["detected_at"])

    db.execute(text("DELETE FROM analysis_results WHERE run_id = :r AND method = :m"),
               {"r": run_id, "m": METHOD})
    for c in candidates:
        db.execute(text("""
            INSERT INTO analysis_results (run_id, method, predicted_cause, detected_at, evidence)
            VALUES (:r, :m, :cause, :at, CAST(:evidence AS jsonb))
        """), {"r": run_id, "m": METHOD, "cause": c["fault_type"],
               "at": c["detected_at"], "evidence": json.dumps(c["evidence"])})
    db.commit()

    return {"run_id": run_id, "method": METHOD, "count": len(candidates), "candidates": candidates}
