"""운영 화면용 API: 서비스 상태판, 인프라 상태, 파드 죽이기.

Ingress에서 이 PC 안의 요청만 통과시키고(k8s/app/ops.yaml), 조작은 토큰까지 있어야 한다.
"""
import hmac
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from . import k8s

OPS_TOKEN = os.environ.get("OPS_TOKEN", "")
GPU_URL = os.environ.get("GPU_METRICS_URL", "http://gpu-metrics:9400")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
DISK_PATH = os.environ.get("DISK_PATH", "/host-disk")
BACKUP_PATH = os.environ.get("BACKUP_PATH", "/backups")
DB_HOST = os.environ.get("DB_HOST", "db")
DB_NAME = os.environ.get("DB_NAME", "")
OPS_DB_PASSWORD = os.environ.get("OPS_DB_PASSWORD", "")
MIB = 1024 ** 2

# 죽여도 되는 서비스만. db는 잠깐 전체가 멈추고, sim은 돌던 장비 상태가 사라진다.
KILLABLE = {"web", "analysis"}
POD_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{0,252}$")

app = FastAPI(title="automachine 운영 API")


@app.middleware("http")
async def refuse_public(request: Request, call_next):
    """Tailscale Funnel은 공개 요청에 이 헤더를 붙인다. Funnel을 켜도 운영 API는 답하지 않는다."""
    if "tailscale-funnel-request" in request.headers:
        return JSONResponse({"detail": "외부에서는 쓸 수 없음"}, status_code=403)
    return await call_next(request)


@app.get("/api/ops/live")
def live():
    return {"status": "ok"}


def seconds_since(stamp):
    if not stamp:
        return None
    return int((datetime.now(timezone.utc) - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds())


def pod_status(pod):
    """kubectl get pods의 STATUS 칸과 같은 뜻으로 만든다."""
    if pod["metadata"].get("deletionTimestamp"):
        return "Terminating"
    status = pod["status"]
    inits = status.get("initContainerStatuses", [])
    for i, c in enumerate(inits):
        state = c.get("state", {})
        if "terminated" in state and state["terminated"].get("exitCode") == 0:
            continue
        waiting = state.get("waiting", {}).get("reason")
        if waiting and waiting != "PodInitializing":
            return f"Init:{waiting}"
        return f"Init:{i}/{len(inits)}"
    for c in status.get("containerStatuses", []):
        state = c.get("state", {})
        if "waiting" in state:
            return state["waiting"].get("reason", "Waiting")
        if "terminated" in state:
            return state["terminated"].get("reason", "Terminated")
    return status.get("phase", "Unknown")


def pod_metrics():
    """파드 이름별 사용량. metrics-server가 아직 준비 안 됐으면 사용량 없이 보여 준다."""
    try:
        items = k8s.get(k8s.namespaced("pods", "/apis/metrics.k8s.io/v1beta1"))["items"]
    except httpx.HTTPError:
        return {}
    usage = {}
    for item in items:
        containers = item["containers"]
        usage[item["metadata"]["name"]] = {
            "cpu_m": sum(k8s.cpu_millicores(c["usage"]["cpu"]) for c in containers),
            "memory_mib": sum(k8s.memory_mib(c["usage"]["memory"]) for c in containers),
        }
    return usage


def last_termination(statuses):
    """이 파드의 컨테이너가 마지막으로 재시작되기 전에 왜 꺼졌는지. 파드를 새로 만들면 기록도 사라진다."""
    ended = [c["lastState"]["terminated"] for c in statuses if "terminated" in c.get("lastState", {})]
    if not ended:
        return None
    last = max(ended, key=lambda t: t.get("finishedAt") or "")
    return {
        "reason": last.get("reason"),
        "exit_code": last.get("exitCode"),
        "seconds_ago": seconds_since(last.get("finishedAt")),
    }


def pod_view(pod, usage):
    statuses = pod["status"].get("containerStatuses", [])
    limits = pod["spec"]["containers"][0].get("resources", {}).get("limits", {})
    used = usage.get(pod["metadata"]["name"], {})
    return {
        "name": pod["metadata"]["name"],
        "status": pod_status(pod),
        "ready": sum(1 for c in statuses if c.get("ready")),
        "containers": len(pod["spec"]["containers"]),
        "restarts": sum(c.get("restartCount", 0) for c in statuses),
        "last_termination": last_termination(statuses),
        "age_s": seconds_since(pod["metadata"].get("creationTimestamp")),
        "cpu_m": used.get("cpu_m"),
        "cpu_limit_m": k8s.cpu_millicores(limits["cpu"]) if "cpu" in limits else None,
        "memory_mib": used.get("memory_mib"),
        "memory_limit_mib": k8s.memory_mib(limits["memory"]) if "memory" in limits else None,
    }


@app.get("/api/ops/overview")
def overview():
    try:
        pods = k8s.get(k8s.namespaced("pods"))["items"]
        workloads = (k8s.get(k8s.namespaced("deployments", "/apis/apps/v1"))["items"]
                     + k8s.get(k8s.namespaced("statefulsets", "/apis/apps/v1"))["items"])
        events = k8s.get(k8s.namespaced("events"))["items"]
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"k8s API 오류: {e}") from None
    usage = pod_metrics()

    services = []
    for w in sorted(workloads, key=lambda w: w["metadata"]["name"]):
        name = w["metadata"]["name"]
        mine = [p for p in pods if p["metadata"].get("labels", {}).get("app") == name]
        image = w["spec"]["template"]["spec"]["containers"][0]["image"]
        services.append({
            "name": name,
            "kind": w["kind"] if "kind" in w else ("StatefulSet" if "volumeClaimTemplates" in w["spec"] else "Deployment"),
            "desired": w["spec"].get("replicas", 0),
            "ready": w.get("status", {}).get("readyReplicas", 0),
            "version": image.rsplit(":", 1)[-1],
            "killable": name in KILLABLE,
            "pods": [pod_view(p, usage) for p in sorted(mine, key=lambda p: p["metadata"]["name"])],
        })

    def when(e):
        return e.get("lastTimestamp") or e.get("eventTime") or e["metadata"].get("creationTimestamp") or ""

    recent = sorted(events, key=when, reverse=True)[:30]
    return {
        "services": services,
        "events": [{
            "at": when(e),
            "type": e.get("type"),
            "reason": e.get("reason"),
            "object": e.get("involvedObject", {}).get("name"),
            "message": e.get("message"),
        } for e in recent],
    }


@app.get("/api/ops/logs/{pod}", response_class=PlainTextResponse)
def logs(pod: str, tail: int = 200):
    if not POD_NAME.match(pod):
        raise HTTPException(status_code=400, detail="파드 이름이 올바르지 않음")
    try:
        return k8s.get_text(k8s.namespaced(f"pods/{pod}/log"), tailLines=min(max(tail, 1), 1000))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="로그를 읽을 수 없음") from None
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"k8s API 오류: {e}") from None


@app.post("/api/ops/services/{service}/kill")
def kill(service: str, x_ops_token: str = Header(default="")):
    if not OPS_TOKEN or not hmac.compare_digest(x_ops_token, OPS_TOKEN):
        raise HTTPException(status_code=401, detail="토큰이 맞지 않음")
    if service not in KILLABLE:
        raise HTTPException(status_code=403, detail=f"{service}는 죽일 수 없음")
    try:
        pods = k8s.get(k8s.namespaced("pods"), labelSelector=f"app={service}")["items"]
        running = [p for p in pods if pod_status(p) == "Running"]
        if not running:
            raise HTTPException(status_code=409, detail="지금 돌고 있는 파드가 없음")
        name = running[0]["metadata"]["name"]
        k8s.delete(k8s.namespaced(f"pods/{name}"))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"k8s API 오류: {e}") from None
    print(f"pod killed from ops page: {name}", flush=True)
    return {"killed": name}


def disk():
    try:
        s = os.statvfs(DISK_PATH)
    except OSError:
        return None
    gib = 1024 ** 3
    return {"total_gib": s.f_blocks * s.f_frsize / gib, "used_gib": (s.f_blocks - s.f_bfree) * s.f_frsize / gib}


def gpu():
    try:
        res = httpx.get(GPU_URL, timeout=6)
        res.raise_for_status()
        return {"gpus": res.json()["gpus"]}
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return {"gpus": [], "error": str(e)}


def ollama():
    try:
        version = httpx.get(f"{OLLAMA_URL}/api/version", timeout=3).json().get("version")
        running = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=3).json().get("models", [])
    except (httpx.HTTPError, ValueError) as e:
        return {"available": False, "error": str(e), "models": []}
    return {
        "available": True,
        "version": version,
        "models": [{"name": m.get("name"), "vram_mib": m.get("size_vram", 0) / 1024 ** 2,
                    "size_mib": m.get("size", 0) / 1024 ** 2} for m in running],
    }


@app.get("/api/ops/infra")
def infra():
    try:
        nodes = k8s.get("/api/v1/nodes")["items"]
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"k8s API 오류: {e}") from None
    try:
        usage = {n["metadata"]["name"]: n["usage"] for n in k8s.get("/apis/metrics.k8s.io/v1beta1/nodes")["items"]}
    except httpx.HTTPError:
        usage = {}

    views = []
    for n in nodes:
        name = n["metadata"]["name"]
        info = n["status"]["nodeInfo"]
        capacity = n["status"]["capacity"]
        used = usage.get(name)
        views.append({
            "name": name,
            "ready": any(c["type"] == "Ready" and c["status"] == "True" for c in n["status"]["conditions"]),
            "os": info["osImage"],
            "kernel": info["kernelVersion"],
            "kubelet": info["kubeletVersion"],
            "runtime": info["containerRuntimeVersion"],
            "arch": info["architecture"],
            "cpu_cores": k8s.cpu_millicores(capacity["cpu"]) / 1000,
            "memory_total_mib": k8s.memory_mib(capacity["memory"]),
            "cpu_used_m": k8s.cpu_millicores(used["cpu"]) if used else None,
            "memory_used_mib": k8s.memory_mib(used["memory"]) if used else None,
        })
    return {"nodes": views, "disk": disk(), "gpu": gpu(), "ollama": ollama()}


def db_usage():
    """ops_reader 계정은 표 내용을 읽을 수 없고, 크기와 연결 수만 본다."""
    try:
        with psycopg.connect(host=DB_HOST, dbname=DB_NAME, user="ops_reader", password=OPS_DB_PASSWORD,
                             connect_timeout=3) as conn:
            size = conn.execute("SELECT pg_database_size(current_database())").fetchone()[0]
            connections = conn.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE backend_type = 'client backend'").fetchone()[0]
            max_connections = conn.execute("SELECT current_setting('max_connections')::int").fetchone()[0]
            tables = conn.execute(
                """SELECT relname, pg_total_relation_size(oid) FROM pg_class
                   WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace
                   ORDER BY 2 DESC LIMIT 5""").fetchall()
    except psycopg.Error as e:
        return {"available": False, "error": type(e).__name__}
    try:
        pvc = k8s.get(k8s.namespaced("persistentvolumeclaims/pgdata-db-0"))
        capacity = k8s.memory_mib(pvc["status"]["capacity"]["storage"])
    except (httpx.HTTPError, KeyError):
        capacity = None
    return {
        "available": True,
        "size_mib": size / MIB,
        "capacity_mib": capacity,
        "connections": connections,
        "max_connections": max_connections,
        "tables": [{"name": name, "size_mib": bytes_ / MIB} for name, bytes_ in tables],
    }


def logs_usage():
    root = Path(DISK_PATH)
    try:
        runs = [p for p in root.iterdir() if p.is_dir()]
        size = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    except OSError as e:
        return {"available": False, "error": type(e).__name__}
    return {"available": True, "size_mib": size / MIB, "runs": len(runs)}


def job_state(job):
    status = job.get("status", {})
    for condition in status.get("conditions", []):
        if condition.get("status") == "True":
            if condition.get("type") == "Complete":
                return "성공"
            if condition.get("type") == "Failed":
                return "실패"
    return "실행 중" if status.get("active") else "대기"


def backup_status():
    # 마지막 성공 시각은 파일로 판단한다. 다 읽어 본 뒤에야 .dump 이름이 붙기 때문이다.
    try:
        found = sorted(Path(BACKUP_PATH).glob("db_*.dump"), key=lambda f: f.stat().st_mtime, reverse=True)
        files = [{"name": f.name, "size_mib": f.stat().st_size / MIB, "age_s": int(time.time() - f.stat().st_mtime)}
                 for f in found]
    except OSError:
        files = []
    try:
        cron = k8s.get(k8s.namespaced("cronjobs/db-backup", "/apis/batch/v1"))
        jobs = [j for j in k8s.get(k8s.namespaced("jobs", "/apis/batch/v1"))["items"]
                if any(o.get("name") == "db-backup" for o in j["metadata"].get("ownerReferences", []))]
    except httpx.HTTPError as e:
        return {"files": files, "error": f"k8s API 오류: {type(e).__name__}"}
    latest = max(jobs, key=lambda j: j["metadata"]["creationTimestamp"], default=None)
    return {
        "files": files,
        "schedule": cron["spec"]["schedule"],
        "time_zone": cron["spec"].get("timeZone"),
        "last_job": latest and {
            "state": job_state(latest),
            "age_s": seconds_since(latest["metadata"]["creationTimestamp"]),
        },
    }


@app.get("/api/ops/storage")
def storage():
    return {"db": db_usage(), "logs": logs_usage(), "backup": backup_status()}
