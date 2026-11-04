"""실시간 감시의 엔진. 돌고 있는 런의 로그 파일을 이어 읽고, 분석 버튼과 같은 판단(규칙·경비원·분류·판단 코드)을 돌린다.
DB를 거치지 않는다. 런이 길어져도 매번 다시 적재하지 않으려는 것이다.
판단 시점까지의 기록만 쓰므로, 노즐 막힘과 온도 센서는 청소한 뒤에야 다시 갈린다.
"""
import csv
import io
import re
from datetime import datetime
from pathlib import Path

from . import foreman, manual, rules

# ingest.py와 같은 형식
EVENT_RE = re.compile(r"^(\S+ \S+) (\w+)\s+(\S+)\s+(.*)$")
ALARM_RE = re.compile(r"^(\S+ \S+) (SET|CLEAR)\s+(\S+)\s+(\S+)\s+(.*?)(?: \| (.*))?$")
ATTR_RE = re.compile(r"(\w+)=(\S+)")

# 원인마다 뒤따라 울릴 수 있는 설비 알람. "설비 알람보다 몇 분 먼저"를 잴 때 쓴다 (안내서의 알람 설명과 같은 짝).
RELATED_ALARMS = {
    "nozzle_clog": {"E3005", "E4001"},
    "temp_sensor_drift": {"E3005", "E4001"},
    "air_bubble": {"E3005", "E4001"},
    "vacuum_leak": {"E3001"},
    "air_supply_drop": {"E3001", "E3005", "E9001"},
    "needle_tip_buildup": {"E4001"},
    "needle_offset": {"E4001"},
    "recipe_pressure_error": {"E3005", "E4001"},
    "recipe_retract_error": {"E4001"},
}
FLOATS = {"fixture_vac_kpa", "disp_pressure_kpa", "disp_temp_c", "syringe_level_pct", "bead_width_mm",
          "bead_offset_mm", "cycle_s", "align_dx_mm", "align_dy_mm", "align_score", "nozzle_height_mm"}


def _time(text):
    return datetime.fromisoformat(text)


def _row(header, values):
    """CSV 한 줄을 DB에서 읽은 행과 같은 모양으로 바꾼다 (빈 칸은 None, 수치는 float, 시각은 datetime)."""
    row = {}
    for key, value in zip(header, values):
        if value == "":
            row[key] = None
        elif key in FLOATS:
            row[key] = float(value)
        elif key in ("timestamp", "start_time", "end_time"):
            row[key] = _time(value)
        elif key in ("disp_valve_open", "vac_retries"):
            row[key] = int(float(value))
        else:
            row[key] = value
    if "timestamp" in row:
        row["ts"] = row.pop("timestamp")
    return row


class _Tail:
    """파일에서 지난번 이후 새로 쓰인 완전한 줄만 돌려준다. 쓰는 도중인 마지막 줄은 다음에 읽는다."""

    def __init__(self, path):
        self.path, self.offset, self.rest = path, 0, ""

    def lines(self):
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8", newline="") as f:
            f.seek(self.offset)
            chunk = f.read()
            self.offset = f.tell()
        text = self.rest + chunk
        *complete, self.rest = text.split("\n")
        return [line.rstrip("\r") for line in complete]


class LiveRun:
    """한 런의 로그를 따라가며 판단 재료를 모은다."""

    def __init__(self, run_dir, recipes):
        self.dir = Path(run_dir)
        self.run_id = self.dir.name
        self.recipes = recipes or {}
        self.parts, self.sensors, self.changes, self.maintenance, self.alarms = [], [], [], [], []
        self._tails = {name: _Tail(self.dir / name)
                       for name in ("production.csv", "sensor_trend.csv", "event.log", "alarm.log")}
        self._headers = {}

    def _csv(self, name, target):
        added = 0
        for line in self._tails[name].lines():
            if not line:
                continue
            values = next(csv.reader(io.StringIO(line)))
            if name not in self._headers:
                self._headers[name] = values
                continue
            target.append(_row(self._headers[name], values))
            added += 1
        return added

    def update(self):
        """새 줄을 읽어 붙인다. 읽은 줄 수를 돌려준다."""
        added = self._csv("production.csv", self.parts) + self._csv("sensor_trend.csv", self.sensors)
        for line in self._tails["event.log"].lines():
            m = EVENT_RE.match(line)
            if not m:
                continue
            ts, _level, unit, message = m.groups()
            if unit == "HMI" and message.startswith("Recipe parameter changed"):
                self.changes.append({"ts": _time(ts), "attrs": dict(ATTR_RE.findall(message))})
            elif unit == "MAINT" and message.startswith("Maintenance done"):
                self.maintenance.append({"ts": _time(ts), "action": dict(ATTR_RE.findall(message)).get("action")})
            added += 1
        for line in self._tails["alarm.log"].lines():
            m = ALARM_RE.match(line)
            if m and m.group(2) == "SET":
                ts, _kind, code, unit, message, detail = m.groups()
                self.alarms.append({"ts": _time(ts), "code": code, "unit": unit, "message": message, "detail": detail})
            added += 1
        if added:
            self.parts.sort(key=lambda p: p["start_time"])   # 제품은 끝난 순서로 기록되므로 시작 순서로 맞춘다
        return added

    def context(self):
        return {"run_id": self.run_id, "recipes": self.recipes, "parts": self.parts, "sensors": self.sensors,
                "changes": self.changes, "maintenance": self.maintenance}

    def now(self):
        return self.sensors[-1]["ts"] if self.sensors else None


def first_evidence(candidates, incident):
    """사건의 첫 경보가 본 수치. 화면이 근거 문장을 만들 때 쓴다."""
    inside = [c for c in candidates if incident["started_at"] <= c["detected_at"] <= incident["last_at"]]
    named = [c for c in inside if c["fault_type"] in incident["rule_names"][:1]]
    chosen = (named or inside or [None])[0]
    return chosen and {"type": chosen["fault_type"], "data": chosen["evidence"]}


def fixed_at(live):
    """노즐 청소가 고장을 고쳤다고 확인된 시각들 (청소 뒤 제품 30개의 폭이 돌아온 때).
    실시간 화면은 이 시각을 넘어 사건을 잇지 않는다. 고친 뒤 다시 생긴 고장을 새 경보로 보이고,
    그 경보가 뒤따른 알람보다 몇 분 먼저였는지를 따로 재려는 것이다.
    확인 시각에서 끊으므로, 청소 직후 확인 전까지 남은 경보(청소 전 제품이 섞인 값)는 앞 사건에 붙는다.
    폭이 돌아오지 않은 청소는 끊지 않는다. 그래야 온도 센서 판단(청소 뒤에도 이어지는 사건)이 그대로다.
    분석 버튼은 이것을 쓰지 않는다. 채점한 사건 묶음을 바꾸지 않으려는 것이다."""
    from . import diagnosis
    cleans = sorted({m["ts"] for m in live.maintenance if m["action"] == "nozzle_clean"})
    checks = (diagnosis.width_recovered_after_clean(live.parts, t) for t in cleans)
    return sorted({c["checked_at"] for c in checks if c and c["recovered"]})


def analyze(live, profile, model):
    """지금까지 읽은 기록으로 사건과 원인을 정하고, 화면에 보낼 경보 목록을 만든다."""
    ctx = live.context()
    rule_hits = rules.run_all(live.run_id, live.sensors, live.parts, live.changes, live.recipes)
    from . import anomaly
    guard = anomaly.detect_anomaly(live.run_id, live.parts, live.sensors, profile)
    alerts = []
    for incident in foreman.judge(ctx, rule_hits, profile, model, fixed_at(live)):
        related = RELATED_ALARMS.get(incident["cause"], set())
        alarm = next((a for a in live.alarms if a["code"] in related and a["ts"] >= incident["started_at"]), None)
        alerts.append({
            "started_at": incident["started_at"].isoformat(),
            "last_at": incident["last_at"].isoformat(),
            "cause": incident["cause"],
            "cause_label": incident["cause_label"],
            "basis": incident["basis"],
            "rule_names": incident["rule_names"],
            "guard_values": incident["guard_values"],
            "tree_guess": incident.get("tree_guess"),
            "evidence": first_evidence(rule_hits + guard, incident),
            "actions": manual.actions_from_file(incident["cause"]),
            "recheck_after_clean": incident["cause"] == "nozzle_clog",
            "first_alarm": alarm and {"code": alarm["code"], "message": alarm["message"], "at": alarm["ts"].isoformat()},
            "lead_min": alarm and round((alarm["ts"] - incident["started_at"]).total_seconds() / 60, 1),
        })
    return alerts
