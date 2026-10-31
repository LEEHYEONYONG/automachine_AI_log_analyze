"""서비스별 요청 지표. Traefik이 내보내는 누적 숫자를 15초마다 읽어 두고, 두 시점의 차이로 계산한다.

Prometheus를 띄우지 않으려고 직접 계산한다. WSL 메모리가 8GB뿐이기 때문이다. 기록은 메모리에만 있어서 ops가 재시작하면 사라진다.
Traefik을 거친 요청만 보인다. 파드끼리 직접 부르는 요청과 부하 시험은 세지 않는다.
"""
import math
import os
import re
import threading
import time
from collections import deque

import httpx

# 10.42.0.1은 파드에서 본 이 PC. Traefik은 PC의 네트워크에서 돈다.
URL = os.environ.get("TRAEFIK_METRICS_URL", "http://10.42.0.1:9100/metrics")
INTERVAL_S = 15
SHORT_S = 60
LONG_S = 300

_LINE = re.compile(
    r"^(traefik_service_requests_total|traefik_service_request_duration_seconds_bucket|traefik_entrypoint_requests_total)"
    r"\{([^}]*)\} (\S+)$")
_LABEL = re.compile(r'(\w+)="([^"]*)"')
# medi-info도 같은 Traefik을 쓰므로 이 네임스페이스만 본다.
_SERVICE = re.compile(r"^automachine-(.+)-\d+@kubernetes$")

# 응답할 파드가 하나도 없으면 Traefik이 입구에서 503을 돌려주고, 서비스별 숫자에는 남지 않는다.
# 그런 전면 장애를 놓치지 않으려고 입구 숫자를 따로 본다. 같은 Traefik을 쓰는 medi-info도 여기에 포함된다.
ALL = "_all"
_ENTRYPOINTS = {"web", "websecure"}

_samples = deque(maxlen=LONG_S // INTERVAL_S + 1)
_error = None


def parse(text):
    """서비스별 {codes: {코드: 누적}, buckets: {le: 누적}}. 웹소켓은 연결이 끝나야 기록되므로 응답 시간에서 뺀다."""
    services = {}
    for line in text.splitlines():
        match = _LINE.match(line)
        if not match:
            continue
        labels = dict(_LABEL.findall(match[2]))
        if labels.get("protocol") != "http":
            continue
        if match[1] == "traefik_entrypoint_requests_total":
            if labels.get("entrypoint") not in _ENTRYPOINTS:
                continue
            name = ALL
        else:
            service = _SERVICE.match(labels.get("service", ""))
            if not service:
                continue
            name = service[1]
        entry = services.setdefault(name, {"codes": {}, "buckets": {}})
        value = float(match[3])
        if match[1] != "traefik_service_request_duration_seconds_bucket":
            entry["codes"][labels["code"]] = entry["codes"].get(labels["code"], 0) + value
        else:
            entry["buckets"][labels["le"]] = entry["buckets"].get(labels["le"], 0) + value
    return services


def _total(entry):
    return sum(entry["codes"].values())


def _restarted(older, newer):
    """누적 숫자가 줄었다면 Traefik이 재시작한 것이다. 그 앞의 기록과는 뺄 수 없다."""
    for name, entry in older.items():
        if _total(entry) > _total(newer.get(name, {"codes": {}})):
            return True
    return False


def _baseline(samples, seconds):
    """가장 최근 시점에서 seconds 안의 가장 오래된 기록. 재시작 전으로는 넘어가지 않는다.
    Traefik을 한동안 못 읽어 공백이 생겨도 바로 앞 기록은 쓴다. 초당 요청은 실제 경과 시간으로 나누므로 맞다."""
    newest = samples[-1]
    base = newest
    for sample in reversed(samples[:-1]):
        too_old = base is not newest and newest["at"] - sample["at"] > seconds + 1
        if too_old or _restarted(sample["services"], base["services"]):
            break
        base = sample
    return base


def _count(new, old, prefix):
    codes = new["codes"]
    return int(sum(v - old["codes"].get(c, 0) for c, v in codes.items() if c.startswith(prefix)))


def _p95(new, old):
    """Traefik의 칸이 0.1, 0.3, 1.2, 5초로 넓어서 추정값 대신 '95%가 이 안에 든 칸'을 돌려준다."""
    changes = sorted(((float(le), v - old["buckets"].get(le, 0)) for le, v in new["buckets"].items()), key=lambda c: c[0])
    if not changes or changes[-1][1] <= 0:
        return None
    for le, cumulative in changes:
        if cumulative >= changes[-1][1] * 0.95:
            return le
    return None


EMPTY = {"codes": {}, "buckets": {}}


def summarize(samples):
    if len(samples) < 2:
        return []
    newest = samples[-1]
    short, long = _baseline(samples, SHORT_S), _baseline(samples, LONG_S)
    elapsed = newest["at"] - short["at"]
    views = []
    for name, entry in sorted(newest["services"].items()):
        recent = short["services"].get(name, EMPTY)
        requests = int(_total(entry) - _total(recent))
        p95 = _p95(entry, recent)
        over = p95 == math.inf  # 맨 끝 칸(+Inf). JSON에는 Infinity를 담을 수 없다.
        views.append({
            "name": name,
            "requests": requests,
            "per_second": requests / elapsed if elapsed > 0 else 0,
            "client_errors": _count(entry, recent, "4"),
            "server_errors": _count(entry, recent, "5"),
            "server_errors_long": _count(entry, long["services"].get(name, EMPTY), "5"),
            "p95_le": None if over else p95,
            "p95_over": over,
        })
    return views


def status():
    samples = list(_samples)
    return {
        "available": _error is None,
        "error": _error,
        "window_s": int(samples[-1]["at"] - _baseline(samples, SHORT_S)["at"]) if samples else 0,
        "long_window_s": int(samples[-1]["at"] - _baseline(samples, LONG_S)["at"]) if samples else 0,
        "services": summarize(samples),
    }


def _collect():
    global _error
    while True:
        try:
            res = httpx.get(URL, timeout=5)
            res.raise_for_status()
            _samples.append({"at": time.monotonic(), "services": parse(res.text)})
            _error = None
        except httpx.HTTPError as e:
            _error = type(e).__name__
        time.sleep(INTERVAL_S)


def start():
    threading.Thread(target=_collect, daemon=True).start()
