"""실시간 감시 서비스. 시뮬레이터에 지금 런을 묻고, 그 로그를 몇 초마다 이어 읽어 경보 목록을 갱신한다.
k8s에서는 이 파드를 1개만 둔다. 분석 파드처럼 여러 개면 파드마다 경보가 달라진다.

    uvicorn app.watch:app --port 8000
"""
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI

from . import anomaly, classify, live
from .config import LOGS_DIR

SIM_URL = os.environ.get("SIM_URL", "http://sim:8000")
# 장비를 빠르게 돌리면 이 간격도 장비 시간으로 늘어난다 (×30이면 3초가 1.5분). 한 번 판단은 8시간치 기록에도 0.1초 안팎이다.
INTERVAL_S = float(os.environ.get("WATCH_INTERVAL_S", "1"))
RECIPES_EVERY_S = 30     # 레시피 표준값은 드물게 바뀌므로 가끔 다시 묻는다

state = {"status": "starting", "run_id": None, "sim_time": None, "sim_speed": None, "alerts": [],
         "error": None, "checked_at": None, "rows": 0}
_lock = threading.Lock()


def _publish(**values):
    with _lock:
        state.update(values, checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _loop():
    profile, model = anomaly.load_profile(), classify.load_model()
    current, recipes_at = None, 0.0
    while True:
        try:
            sim = httpx.get(f"{SIM_URL}/api/state", timeout=5).json()["sim"]
            run_id = sim["run_id"]
            if current is None or current.run_id != run_id or time.monotonic() - recipes_at > RECIPES_EVERY_S:
                recipes = httpx.get(f"{SIM_URL}/api/recipes", timeout=5).json()["recipes"]
                recipes_at = time.monotonic()
                if current is None or current.run_id != run_id:
                    current = live.LiveRun(Path(LOGS_DIR) / run_id, recipes)   # 새 런이면 처음부터 읽는다
                else:
                    current.recipes = recipes
            if current.update() or state["status"] != "watching":
                alerts = live.analyze(current, profile, model)
                now = current.now()
                _publish(status="watching", run_id=run_id, alerts=alerts, error=None,
                         sim_time=now and now.isoformat(), sim_speed=sim.get("speed"), rows=len(current.sensors))
            else:
                _publish(sim_speed=sim.get("speed"))
        except Exception as e:    # 감시가 멈추면 안 되므로 어떤 오류든 기록만 하고 다음 차례에 다시 시도한다
            print(f"watch error: {type(e).__name__}: {e}", flush=True)
            _publish(status="error", error=f"{type(e).__name__}: {e}"[:200])
        time.sleep(INTERVAL_S)


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=_loop, daemon=True).start()
    yield


app = FastAPI(title="automachine 실시간 감시", lifespan=lifespan)


@app.get("/api/analysis/watch")
def watch():
    with _lock:
        return dict(state)


@app.get("/api/analysis/watch/live")
def watch_live():
    return {"status": "ok"}
