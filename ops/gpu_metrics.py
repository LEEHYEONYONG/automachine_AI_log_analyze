"""nvidia-smi 결과를 JSON으로 내보내는 작은 서버 (포트 9400).

WSL에서는 특권 파드에서만 GPU를 읽을 수 있어서, k8s 권한이 있는 ops와 나눠 따로 띄운다.
이 파드에는 k8s 토큰을 넣지 않고, nvidia-smi 조회 외에는 아무것도 하지 않는다.
"""
import json
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SMI = "/usr/lib/wsl/lib/nvidia-smi"
FIELDS = ["name", "driver_version", "memory.total", "memory.used", "utilization.gpu", "temperature.gpu", "power.draw"]
KEYS = ["name", "driver", "memory_total_mib", "memory_used_mib", "utilization_pct", "temperature_c", "power_w"]


def number(text):
    try:
        return float(text)
    except ValueError:
        return None   # 카드에 따라 "[N/A]"가 온다


def read_gpus():
    out = subprocess.run(
        [SMI, f"--query-gpu={','.join(FIELDS)}", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=5, check=True,
    ).stdout
    gpus = []
    for line in out.strip().splitlines():
        values = [v.strip() for v in line.split(",")]
        gpus.append({k: (v if k in ("name", "driver") else number(v)) for k, v in zip(KEYS, values)})
    return gpus


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            status, body = 200, {"status": "ok"}
        else:
            try:
                status, body = 200, {"gpus": read_gpus()}
            except (subprocess.SubprocessError, OSError) as e:
                status, body = 503, {"error": str(e)}
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass   # 몇 초마다 불리므로 로그를 남기지 않는다


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9400), Handler).serve_forever()
