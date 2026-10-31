import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..database import get_db
from ..config import OLLAMA_URL

# /api/analysis so the web proxy can tell it apart from the simulator's /api
router = APIRouter(
    prefix="/api/analysis",
    tags=["Health"]
)


@router.get("/health")
def health(db: Session = Depends(get_db)):
    result = {}

    # DB: 테이블 수와 pgvector 버전
    try:
        count = db.execute(text(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
        )).scalar()
        vector = db.execute(text(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )).scalar()
        result["db"] = f"ok (테이블 {count}개, pgvector {vector})"
    except Exception as e:
        result["db"] = f"실패: {e}"

    # Ollama: 설치된 모델 목록을 받아 본다
    try:
        res = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in res.json()["models"]]
        result["ollama"] = f"ok ({', '.join(models)})"
    except Exception as e:
        result["ollama"] = f"실패: {e}"

    return result


@router.get("/live")
def live():
    """k8s liveness: 프로세스가 응답하는가. DB가 죽었다고 이 앱을 재시작해도 소용없으니 DB는 보지 않는다."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    """k8s readiness: 요청을 받아도 되는가. DB에 못 붙으면 503을 돌려 트래픽을 받지 않는다."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="DB에 연결할 수 없음") from None
    return {"status": "ok"}
