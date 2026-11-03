"""k8s API 호출. 파드에 들어 있는 이 서비스 전용 계정(ServiceAccount)의 토큰을 쓴다.
할 수 있는 일은 k8s/app/ops.yaml의 Role이 정한다. 여기서 막지 않아도 k8s가 거절한다."""
from pathlib import Path

import httpx

ACCOUNT = Path("/var/run/secrets/kubernetes.io/serviceaccount")
API = "https://kubernetes.default.svc"
NAMESPACE = "automachine"


def _request(method, path, headers=None, **kwargs):
    # 토큰은 k8s가 주기적으로 바꾸므로 매번 읽는다
    headers = {"Authorization": f"Bearer {(ACCOUNT / 'token').read_text()}", **(headers or {})}
    res = httpx.request(method, f"{API}{path}", headers=headers, verify=str(ACCOUNT / "ca.crt"), timeout=5, **kwargs)
    res.raise_for_status()
    return res


def get(path, **params):
    return _request("GET", path, params=params).json()


def get_text(path, **params):
    return _request("GET", path, params=params).text


def delete(path):
    return _request("DELETE", path).json()


def post(path, body):
    return _request("POST", path, json=body).json()


def patch(path, body, content_type):
    """content_type: 바꿀 칸만 보내면 합쳐 주는 strategic-merge-patch, 또는 경로를 짚어 바꾸는 json-patch."""
    return _request("PATCH", path, json=body, headers={"Content-Type": f"application/{content_type}+json"}).json()


def namespaced(resource, group="/api/v1"):
    return f"{group}/namespaces/{NAMESPACE}/{resource}"


def cpu_millicores(text):
    """k8s의 CPU 표기(250m, 123456789n, 2)를 밀리코어로."""
    if text.endswith("n"):
        return int(text[:-1]) / 1_000_000
    if text.endswith("u"):
        return int(text[:-1]) / 1_000
    if text.endswith("m"):
        return float(text[:-1])
    return float(text) * 1000


def memory_mib(text):
    """k8s의 메모리 표기(1536Mi, 8123456Ki, 1Gi, 1000000)를 MiB로."""
    units = {"Ki": 1 / 1024, "Mi": 1, "Gi": 1024, "Ti": 1024 ** 2, "k": 1000 / 1024 ** 2, "M": 1000 ** 2 / 1024 ** 2,
             "G": 1000 ** 3 / 1024 ** 2}
    for unit, factor in units.items():
        if text.endswith(unit):
            return float(text[:-len(unit)]) * factor
    return float(text) / 1024 ** 2
