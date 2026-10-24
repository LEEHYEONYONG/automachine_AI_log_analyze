from fastapi import FastAPI
from .routes import health, runs

app = FastAPI(title="automachine 로그 분석 API")

app.include_router(health.router)
app.include_router(runs.router)
