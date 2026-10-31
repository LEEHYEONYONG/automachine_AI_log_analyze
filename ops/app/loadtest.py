"""HPA를 보여 주기 위한 부하 시험. 정해진 주소에 정해진 시간만 요청을 보내고 저절로 끝난다.

분석 API에서 가장 가벼운 /live를 부른다. DB에 부담을 주지 않고 분석 파드의 CPU만 올리기 위해서다.
그래서 실제 분석 작업의 부하와는 다르다.
"""
import os
import threading
import time

import httpx

URL = os.environ.get("LOADTEST_URL", "http://analysis:8000/api/analysis/live")
WORKERS = 4  # ops 자신의 CPU 한도(500m)를 다 쓰면 운영 화면이 느려진다
DURATION_S = 150

_lock = threading.Lock()
_stop = threading.Event()
_state = {"running": False, "active": 0, "started_at": None, "ended_at": None, "requests": 0, "errors": 0}


def _worker(deadline):
    # 연결을 재사용하면 Service가 처음 고른 파드로만 계속 보내므로, 요청마다 새로 연결한다.
    with httpx.Client(timeout=5, headers={"Connection": "close"}) as client:
        while not _stop.is_set() and time.monotonic() < deadline:
            try:
                ok = client.get(URL).status_code == 200
            except httpx.HTTPError:
                ok = False
            with _lock:
                _state["requests"] += 1
                _state["errors"] += 0 if ok else 1
    with _lock:
        _state["active"] -= 1
        if _state["active"] == 0:
            _state["running"] = False
            _state["ended_at"] = time.time()


def start():
    """이미 돌고 있으면 False."""
    with _lock:
        if _state["running"]:
            return False
        _stop.clear()
        _state.update(running=True, active=WORKERS, started_at=time.time(), ended_at=None, requests=0, errors=0)
    deadline = time.monotonic() + DURATION_S
    for _ in range(WORKERS):
        threading.Thread(target=_worker, args=(deadline,), daemon=True).start()
    return True


def stop():
    _stop.set()


def status():
    with _lock:
        state = dict(_state)
    started = state["started_at"]
    return {
        "running": state["running"],
        "duration_s": DURATION_S,
        "elapsed_s": int((state["ended_at"] or time.time()) - started) if started else None,
        "requests": state["requests"],
        "errors": state["errors"],
    }
