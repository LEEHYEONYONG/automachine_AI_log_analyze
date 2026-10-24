from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..database import get_db

router = APIRouter(
    prefix="/api/analysis",
    tags=["Runs"]
)


@router.get("/runs")
def list_runs(db: Session = Depends(get_db)):
    """DB에 적재된 실행 목록과 테이블별 행 수"""
    rows = db.execute(text("""
        SELECT r.run_id, r.machine_id, r.start_time, r.end_time, r.loaded_at,
               (SELECT count(*) FROM events e WHERE e.run_id = r.run_id) AS events,
               (SELECT count(*) FROM alarms a WHERE a.run_id = r.run_id) AS alarms,
               (SELECT count(*) FROM production p WHERE p.run_id = r.run_id) AS production,
               (SELECT count(*) FROM sensor_trend s WHERE s.run_id = r.run_id) AS sensor_trend
        FROM runs r
        ORDER BY r.start_time
    """)).mappings().all()
    return list(rows)
