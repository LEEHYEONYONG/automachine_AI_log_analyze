import json
import re

from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..config import LOGS_DIR
from ..database import engine, get_db
from .. import anomaly, classify, foreman, ingest, rules

router = APIRouter(
    prefix="/api/analysis",
    tags=["Analysis"]
)


def rule_candidates(db, run_id, recipes):
    """규칙 7개를 한 런에 돌린다."""
    sensors = db.execute(text("""
        SELECT ts, mode, disp_valve_open, disp_pressure_kpa, fixture_vac_kpa
        FROM sensor_trend WHERE run_id = :r ORDER BY ts
    """), {"r": run_id}).mappings().all()
    parts = db.execute(text("""
        SELECT start_time, recipe, bead_width_mm, bead_offset_mm, disp_pressure_kpa, ng_reason
        FROM production WHERE run_id = :r ORDER BY start_time
    """), {"r": run_id}).mappings().all()
    changes = db.execute(text("""
        SELECT ts, attrs FROM events
        WHERE run_id = :r AND unit = 'HMI' AND message LIKE 'Recipe parameter changed%' ORDER BY ts
    """), {"r": run_id}).mappings().all()
    return rules.run_all(run_id, sensors, parts, changes, recipes)


RUN_ID = re.compile(r"^\d{8}_\d{4}_[0-9a-f]{6}$")


@router.post("/runs/{run_id}/ingest")
def ingest_run(run_id: str):
    """돌고 있는 런을 지금 상태 그대로 DB에 적재한다. 실시간 경보에서 반장 보고서를 쓰기 전에 부른다.
    같은 런을 다시 적재하면 이전 행을 지우고 새로 넣는다. 로그(logs/)만 읽는다."""
    run_dir = Path(LOGS_DIR) / run_id
    if not RUN_ID.match(run_id) or not (run_dir / "machine_info.json").is_file():
        raise HTTPException(status_code=404, detail=f"적재할 런이 없음: {run_id}")
    conn = engine.raw_connection()
    try:
        with conn.driver_connection.cursor() as cur:
            ingest.load_run(cur, run_dir)
        conn.commit()
    finally:
        conn.close()
    return {"run_id": run_id, "loaded": True}


def _require_run(db, run_id):
    if not db.execute(text("SELECT 1 FROM runs WHERE run_id = :r"), {"r": run_id}).first():
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")


def _require_profile():
    profile = anomaly.load_profile()
    if not profile:
        raise HTTPException(status_code=503, detail="평소 모습이 아직 없음: app.train_anomaly를 먼저 실행")
    return profile


def _require_model():
    model = classify.load_model()
    if not model:
        raise HTTPException(status_code=503, detail="분류 모델이 아직 없음: app.train_classifier를 먼저 실행")
    return model


@router.post("/runs/{run_id}")
def analyze_run(run_id: str, method: Literal["rule", "anomaly", "classify"] = "rule", db: Session = Depends(get_db)):
    """런 하나를 분석해 고장 후보를 찾고 analysis_results에 저장한다.
    method=rule은 규칙 7개(고장 이름까지), method=anomaly는 이상 탐지(평소와 다른 값만),
    method=classify는 이상 탐지가 울린 순간을 결정 트리가 분류(고장 이름까지).
    같은 런을 같은 방법으로 다시 분석하면 이전 결과는 지우고 새로 쓴다."""
    _require_run(db, run_id)
    if method == "rule":
        ctx = classify.load_context(db, run_id)
        candidates = rule_candidates(db, run_id, ctx["recipes"])
    else:
        profile = _require_profile()
        ctx = classify.load_context(db, run_id)
        if method == "anomaly":
            candidates = anomaly.detect_anomaly(run_id, ctx["parts"], ctx["sensors"], profile)
        else:
            candidates = classify.classify_run(ctx, profile, _require_model())
    candidates.sort(key=lambda c: c["detected_at"])

    db.execute(text("DELETE FROM analysis_results WHERE run_id = :r AND method = :m"),
               {"r": run_id, "m": method})
    for c in candidates:
        db.execute(text("""
            INSERT INTO analysis_results (run_id, method, predicted_cause, detected_at, confidence, evidence)
            VALUES (:r, :m, :cause, :at, :confidence, CAST(:evidence AS jsonb))
        """), {"r": run_id, "m": method, "cause": c["fault_type"], "at": c["detected_at"],
               "confidence": c.get("confidence"), "evidence": json.dumps(c["evidence"])})
    db.commit()

    return {"run_id": run_id, "method": method, "count": len(candidates), "candidates": candidates}


def _incidents(db, run_id):
    """규칙·경비원 경보를 사건으로 묶고, 첫 경보 순간의 분류 의견과 코드가 정한 원인을 붙인다."""
    _require_run(db, run_id)
    profile = _require_profile()
    ctx = classify.load_context(db, run_id)
    return ctx, foreman.judge(ctx, rule_candidates(db, run_id, ctx["recipes"]), profile, classify.load_model())


@router.get("/runs/{run_id}/incidents")
def list_incidents(run_id: str, db: Session = Depends(get_db)):
    """이 런의 사건 목록과 이미 쓴 반장 보고서."""
    _, incidents = _incidents(db, run_id)
    saved = db.execute(text("""
        SELECT detected_at, predicted_cause, report, evidence, model, created_at FROM analysis_results
        WHERE run_id = :r AND method = 'foreman'
    """), {"r": run_id}).mappings().all()
    by_time = {s["detected_at"]: s for s in saved}
    for incident in incidents:
        s = by_time.get(incident["started_at"])
        incident["report"] = _saved_view(s) if s else None
    return {"run_id": run_id, "incidents": incidents}


def _saved_view(saved):
    return {**saved["evidence"], "cause": saved["predicted_cause"], "report": saved["report"],
            "model": saved["model"], "written_at": saved["created_at"]}


@router.post("/runs/{run_id}/incidents/report")
def write_report(run_id: str, at: datetime, db: Session = Depends(get_db)):
    """사건 하나의 기록을 반장(LLM)이 조회해 설명을 쓰고 저장한다. 1분 안팎 걸린다. at은 사건의 첫 경보 시각.
    원인은 코드가 이미 정했으며 LLM이 바꾸지 못한다."""
    ctx, incidents = _incidents(db, run_id)
    incident = next((i for i in incidents if i["started_at"] == at), None)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"그 시각에 시작한 사건이 없음: {at}")
    db.commit()   # LLM을 기다리는 동안 읽기 트랜잭션을 열어 두지 않는다

    try:
        result = foreman.run(db, ctx, incident)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
        # 반장이 없어도 규칙·경비원 결과는 그대로 볼 수 있다. 이 요청만 실패로 돌려준다.
        raise HTTPException(status_code=503, detail=f"반장이 답하지 못함: {type(e).__name__}") from None

    db.execute(text("DELETE FROM analysis_results WHERE run_id = :r AND method = 'foreman' AND detected_at = :at"),
               {"r": run_id, "at": at})
    evidence = {k: result[k] for k in ("cause_label", "basis", "reasoning", "doubts", "actions", "tools_called",
                                       "manual_sections", "unverified_numbers", "other_causes")}
    db.execute(text("""
        INSERT INTO analysis_results (run_id, method, predicted_cause, detected_at, evidence, report, model)
        VALUES (:r, 'foreman', :cause, :at, CAST(:evidence AS jsonb), :report, :model)
    """), {"r": run_id, "cause": result["cause"], "at": at, "evidence": json.dumps(evidence, ensure_ascii=False),
           "report": result["report"], "model": result["model"]})
    db.commit()
    return {"run_id": run_id, "started_at": at, **result}
