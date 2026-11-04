# 반장 (3주차). 규칙·경비원·분류의 의견이 모인 사건 하나를 받아 원인을 정하고, LLM이 기록을 조회해 근거를 설명한다.
# 사건과 원인은 코드가 정한다(decide). LLM에게 원인을 고르게 했더니 dev에서 규칙보다 나빴다: 21/33, 24/36 대 규칙 30/36 (eval/README.md 7절).
# LLM은 읽기 전용 함수만 부를 수 있고, 원인·장비·DB를 바꾸지 못한다. 대신 판단과 맞지 않는 기록을 "의문점"으로 적을 수 있다.
# 런 전체를 볼 수 있는 사후 보고이므로 "그 시각에 미리 알았다"는 탐지 점수와 섞지 않는다.
import json
import re
import statistics
from datetime import timedelta

import httpx
from sqlalchemy import text

from . import diagnosis, manual
from .config import LLM_MODEL, OLLAMA_URL
from .classify import NO_FAULT, UNKNOWN

GROUP = timedelta(minutes=60)       # 같은 사건으로 묶는 간격 (eval/README.md의 60분과 같음)
BEFORE = timedelta(minutes=30)      # 사건 전 값과 비교할 구간
WORK_LOOK = timedelta(minutes=60)   # 사건 전후로 살필 작업 기록 범위
MAX_STEPS = 6                       # 함수를 부르는 왕복 횟수 상한. 넘으면 모은 근거로 바로 답을 쓴다
LLM_TIMEOUT = 180
NUM_CTX = 8192                      # 기본 4096은 함수 설명과 결과를 담기에 부족하다

FAULT_NAMES = {
    "nozzle_clog": "노즐 막힘",
    "vacuum_leak": "진공 패드 누설",
    "temp_sensor_drift": "온도 센서 드리프트",
    "air_bubble": "시린지 기포",
    "needle_tip_buildup": "니들 끝 접착제 누적",
    "needle_offset": "니들 높이·위치 틀어짐",
    "air_supply_drop": "공장 에어 공급압 저하",
    "recipe_pressure_error": "레시피 압력 오입력",
    "recipe_retract_error": "레시피 대기 시간 오입력",
    NO_FAULT: "고장 아님",
    UNKNOWN: "판단 불가",
}

SYSTEM_PROMPT = """너는 디스펜싱 장비 라인의 반장이다. 경보가 울린 사건의 원인은 분석 코드가 이미 정했고, 너는 그것을 바꾸지 못한다.
할 일은 작업자가 확인할 수 있게 기록에서 근거를 찾아 설명하는 것이다.
규칙:
- 먼저 함수를 불러 기록을 본다. get_readings와 get_defects는 반드시 부른다.
- 실제로 기록에 있는 것만 쓴다. 값이 서서히 변했는지는 기록에서 확인되지 않으면 쓰지 않는다.
- 주어진 내용과 함수 결과에 없는 수치를 지어내지 않는다.
- 코드의 판단과 맞지 않는 기록을 보면 숨기지 말고 의문점으로 적는다."""

ANSWER_PROMPT = """지금까지 본 기록으로 설명을 끝내라. 정해진 원인은 {cause}이다. JSON으로만 답한다.
reasoning: 이 원인을 뒷받침하는 기록 2~4문장. 다른 고장 이름을 근거로 들지 않는다. 한국어로, 함수 결과의 수치를 그대로 인용한다.
{clean_note}doubts: 이 원인과 맞지 않는 기록 0~2문장. 없으면 빈 목록."""

TOOLS = [
    {"type": "function", "function": {
        "name": "get_readings",
        "description": "사건 전 30분과 사건 중의 비드 폭, 오프셋, 토출 압력, 진공, 표시 온도 중앙값을 비교한다.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_defects",
        "description": "사건 전 30분과 사건 중의 불량 사유별 개수를 비교한다.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_alarms",
        "description": "사건 앞뒤에 난 장비 알람을 코드, 시각, 상세와 함께 보여 준다.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_work_history",
        "description": "사건 앞뒤의 정비 작업과 레시피 설정 변경 기록을 보여 준다. 변경 값이 표준에서 얼마나 벗어났는지도 알려 준다.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "check_after_clean",
        "description": "노즐 청소 뒤 비드 폭이 돌아왔는지 본다. 노즐 막힘과 온도 센서 드리프트를 가를 때만 쓴다.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "search_manual",
        "description": "점검 안내서에서 증상, 구별법, 조치를 찾는다.",
        "parameters": {"type": "object", "required": ["question"],
                       "properties": {"question": {"type": "string", "description": "찾을 내용. 예: 진공과 압력이 함께 떨어짐"}}},
    }},
]


def incidents(rule_candidates, guard_candidates, breaks=()):
    """규칙과 경비원의 경보를 사건으로 묶는다.
    같은 규칙이 60분 안에 반복되면 같은 사건이고, 새 규칙 이름이 나오면 다른 고장일 수 있으니 새 사건이다.
    경비원 경보는 이름이 없어서 가장 최근의 열린 사건에 붙고, 열린 사건이 없으면 새 사건이 된다.
    breaks: 이 시각을 넘어서는 사건을 잇지 않는다 (실시간 감시만 쓴다. 분석 버튼은 비워 둔다)."""
    alerts = [("rule", c) for c in rule_candidates] + [("guard", c) for c in guard_candidates]
    alerts.sort(key=lambda x: x[1]["detected_at"])
    result = []
    for kind, c in alerts:
        at = c["detected_at"]
        opened = [i for i in result
                  if at - i["last_at"] <= GROUP and not any(i["last_at"] < b <= at for b in breaks)]
        target = None
        if kind == "guard":
            target = opened[-1] if opened else None
        else:
            same = [i for i in opened if c["fault_type"] in i["rule_names"]]
            unnamed = [i for i in opened if not i["rule_names"]]
            target = same[-1] if same else (unnamed[-1] if unnamed else None)
        if target is None:
            target = {"started_at": at, "last_at": at, "rule_names": [], "guard_values": [], "notes": [], "alerts": 0}
            result.append(target)
        target["last_at"] = at
        target["alerts"] += 1
        if kind == "rule" and c["fault_type"] not in target["rule_names"]:
            target["rule_names"].append(c["fault_type"])
            target["notes"].append(f"규칙 {c['fault_type']}: {_plain(c['evidence'])}")
        if kind == "guard" and c["evidence"]["feature"] not in target["guard_values"]:
            target["guard_values"].append(c["evidence"]["feature"])
            target["notes"].append(f"경비원 {c['evidence']['feature']}: {_plain(c['evidence'])}")
    return result


def _plain(evidence):
    """경보가 본 수치를 한 줄로. 경보가 처음 울린 때의 값이다."""
    def show(v):
        return round(v, 3) if isinstance(v, float) else v
    return ", ".join(f"{k}={show(v)}" for k, v in evidence.items() if k not in ("feature", "recipe"))


def after_clean(ctx, incident):
    """사건 뒤 첫 노즐 청소의 결과. (청소 시각, width_recovered_after_clean의 결과). 청소가 없으면 (None, None)."""
    cleans = [m["ts"] for m in ctx["maintenance"] if m["action"] == "nozzle_clean" and m["ts"] >= incident["started_at"]]
    if not cleans:
        return None, None
    return cleans[0], diagnosis.width_recovered_after_clean(ctx["parts"], cleans[0])


def decide(ctx, incident, tree_guess):
    """사건의 원인을 코드로 정한다. (원인, 정한 이유)
    규칙 이름이 있으면 첫 이름을 쓴다. 규칙이 노즐 막힘이라 했는데 청소 뒤 폭이 안 돌아왔으면 온도 센서로 바꾼다.
    규칙 이름이 없으면 분류 의견을 쓰고, 그것도 없으면 판단 불가다."""
    if incident["rule_names"]:
        cause = incident["rule_names"][0]
        if cause == "nozzle_clog":
            _, result = after_clean(ctx, incident)
            if result and not result["recovered"]:
                return "temp_sensor_drift", (f"규칙은 노즐 막힘이지만 청소 뒤 폭이 돌아오지 않음 "
                                             f"({result['width_before_clean_mm']:.3f} → {result['width_after_clean_mm']:.3f} mm)")
        return cause, f"규칙 {cause}"
    if tree_guess in FAULT_NAMES and tree_guess != UNKNOWN:
        return tree_guess, "규칙 경보 없음, 분류 모델 의견"
    return UNKNOWN, "규칙 경보가 없고 분류 모델도 확신하지 못함"


def judge(ctx, rule_candidates, profile, model, breaks=()):
    """규칙·경비원 경보를 사건으로 묶고, 첫 경보 순간의 분류 의견과 코드가 정한 원인을 붙인다.
    분석 버튼(DB의 행)과 실시간 감시(파일에서 이어 읽은 행)가 같은 판단을 하도록 둘 다 이 함수를 쓴다.
    breaks는 실시간 감시만 넘긴다 (live.fixed_at)."""
    from . import anomaly, classify    # classify가 이 모듈을 쓰지 않도록 여기서 읽는다

    guard = anomaly.detect_anomaly(ctx["run_id"], ctx["parts"], ctx["sensors"], profile)
    found = incidents(rule_candidates, guard, breaks)
    if model:
        pairs = classify.alert_snapshots(ctx, profile)
        for incident in found:
            first = next((row for alert, row in pairs
                          if incident["started_at"] <= alert["detected_at"] <= incident["last_at"]), None)
            if first:
                name, confidence = classify.predict(model, first)
                incident["tree_guess"] = name if confidence >= classify.MIN_CONFIDENCE else classify.UNKNOWN
                incident["tree_confidence"] = round(confidence, 2)
    for incident in found:
        incident["cause"], incident["basis"] = decide(ctx, incident, incident.get("tree_guess"))
        incident["cause_label"] = FAULT_NAMES[incident["cause"]]
    return found


def _median(rows, key):
    values = [r[key] for r in rows if r[key] is not None]
    return round(statistics.median(values), 3) if values else None


class Tools:
    """함수 하나가 짧은 글 하나를 돌려준다. 시간 범위는 코드가 사건에서 정하므로 LLM이 시각을 틀릴 일이 없다."""

    def __init__(self, db, ctx, incident):
        self.db, self.ctx, self.incident = db, ctx, incident
        self.start, self.end = incident["started_at"], incident["last_at"]
        self.results = []        # 답의 수치를 검사할 때 쓰는 자료: 함수 결과. 사건 설명은 run()이 넣는다
        self.called = []
        self.manual_sections = []

    def _before(self):
        return [p for p in self.ctx["parts"] if self.start - BEFORE <= p["start_time"] < self.start]

    def _during(self):
        # 경보 하나뿐인 사건도 값을 볼 수 있게 경보 뒤 제품 30개까지 포함한다.
        after = [p for p in self.ctx["parts"] if p["start_time"] > self.end][:30]
        return [p for p in self.ctx["parts"] if self.start <= p["start_time"] <= self.end] + after

    def get_readings(self):
        before, during = self._before(), self._during()
        lines = [f"제품 수: 사건 전 {len(before)}개, 사건 중 {len(during)}개"]
        for label, key in [("비드 폭 mm", "bead_width_mm"), ("오프셋 mm", "bead_offset_mm"),
                           ("토출 압력 kPa", "disp_pressure_kpa"), ("진공 kPa", "fixture_vac_kpa"),
                           ("표시 온도 C", "disp_temp_c")]:
            lines.append(f"{label}: 사건 전 {_median(before, key)} → 사건 중 {_median(during, key)}")
        return "\n".join(lines)

    def get_defects(self):
        def count(parts):
            reasons = {}
            for p in parts:
                if p["ng_reason"]:
                    reasons[p["ng_reason"]] = reasons.get(p["ng_reason"], 0) + 1
            return reasons or "없음"
        return f"사건 전 30분: {count(self._before())}\n사건 중: {count(self._during())}"

    def get_alarms(self):
        rows = self.db.execute(text("""
            SELECT code, set_ts, message, detail FROM alarms
            WHERE run_id = :r AND set_ts BETWEEN :a AND :b ORDER BY set_ts LIMIT 12
        """), {"r": self.ctx["run_id"], "a": self.start - WORK_LOOK, "b": self.end + WORK_LOOK}).mappings().all()
        if not rows:
            return "사건 앞뒤 60분에 알람 없음"
        return "\n".join(f"{r['set_ts']:%H:%M:%S} {r['code']} {r['message']} {r['detail'] or ''}" for r in rows)

    def get_work_history(self):
        a, b = self.start - WORK_LOOK, self.end + WORK_LOOK
        lines = [f"{m['ts']:%H:%M:%S} 정비 완료: {m['action']}" for m in self.ctx["maintenance"] if a <= m["ts"] <= b]
        for c in self.ctx["changes"]:
            if a <= c["ts"] <= b:
                v = c["attrs"]
                standard = self.ctx["recipes"].get(v["recipe"], {}).get(v["param"])
                lines.append(f"{c['ts']:%H:%M:%S} 설정 변경: {v['param']} {v['old']} → {v['new']} (표준 {standard})")
        for e in self.ctx.get("machine_events", []):
            if a <= e["ts"] <= b:
                v = e["attrs"]
                if e["message"].startswith("Setting changed"):
                    lines.append(f"{e['ts']:%H:%M:%S} 장비 설정 변경: {v.get('param')} {v.get('old')} → {v.get('new')}")
                elif e["message"].startswith("Run mode change"):
                    lines.append(f"{e['ts']:%H:%M:%S} 운전 방식 변경: {v.get('run_mode')}")
                else:
                    lines.append(f"{e['ts']:%H:%M:%S} 더미 런 끝: {v.get('count')}개")
        lines.sort()
        return "\n".join(lines) or "사건 앞뒤 60분에 정비와 설정 변경 기록 없음"

    def check_after_clean(self):
        clean_at, result = after_clean(self.ctx, self.incident)
        if clean_at is None:
            return "사건 뒤 노즐 청소 기록이 없어 확인할 수 없음"
        if result is None:
            return f"{clean_at:%H:%M:%S} 청소 뒤 제품이 30개가 안 되어 확인할 수 없음"
        state = "돌아옴" if result["recovered"] else "돌아오지 않음"
        # 폭은 에어나 압력 설정이 돌아와도 돌아온다. 그래서 "의심: 고장 이름"을 말하지 않는다.
        return (f"{clean_at:%H:%M:%S} 청소 전 폭 {result['width_before_clean_mm']:.3f} mm → "
                f"청소 후 {result['width_after_clean_mm']:.3f} mm, 폭이 {state}.")

    def search_manual(self, question=""):
        hits = manual.search(self.db, question or "고장 점검")
        self.manual_sections += [h["section"] for h in hits]
        return "\n\n".join(f"[{h['section']}]\n{h['content']}" for h in hits)

    def call(self, name, arguments):
        allowed = {t["function"]["name"] for t in TOOLS}
        if name not in allowed:
            return f"없는 함수입니다: {name}"
        # 모델이 인자를 잘못 넘겨도 함수가 죽지 않도록 필요한 인자만 꺼낸다.
        output = self.search_manual(str(arguments.get("question", ""))) if name == "search_manual" else getattr(self, name)()
        self.called.append(name)
        self.results.append(output)
        return output


def _chat(messages, **extra):
    res = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=LLM_TIMEOUT, json={
        "model": LLM_MODEL, "messages": messages, "stream": False,
        "options": {"temperature": 0, "num_ctx": NUM_CTX}, **extra})
    res.raise_for_status()
    return res.json()["message"]


def _briefing(incident):
    rule = ", ".join(incident["rule_names"]) or "없음"
    guard = ", ".join(incident["guard_values"]) or "없음"
    notes = "\n".join(f"- {n}" for n in incident["notes"])
    return (f"사건 시각: {incident['started_at']:%H:%M:%S} ~ {incident['last_at']:%H:%M:%S}, 경보 {incident['alerts']}개\n"
            f"코드가 정한 원인: {incident['cause']} ({FAULT_NAMES[incident['cause']]}). 이유: {incident['basis']}\n"
            f"규칙 의견: {rule}\n경비원이 평소와 다르다고 본 값: {guard}\n"
            f"경보가 처음 울렸을 때의 수치:\n{notes}")


def unverified_numbers(sentences, tool_results):
    """근거 문장의 수치 중 함수 결과에 없는 것. 지어낸 숫자를 화면에서 표시하려고 코드가 검사한다."""
    source = {float(n) for n in re.findall(r"\d+(?:\.\d+)?", "\n".join(tool_results))}   # 0.750과 0.75는 같은 수
    return sorted({n for s in sentences for n in re.findall(r"\d+(?:\.\d+)?", s) if float(n) not in source})


def other_causes_mentioned(sentences, cause):
    """근거 문장에 나온, 정해진 원인이 아닌 고장 이름. 설명이 판단과 어긋나는지 화면에서 표시하려고 코드가 검사한다."""
    joined = "\n".join(sentences)
    return sorted(name for name, label in FAULT_NAMES.items()
                  if name not in (cause, NO_FAULT, UNKNOWN) and (name in joined or label in joined))


def actions_for(db, cause):
    """조치는 LLM이 쓰지 않고 안내서의 문장을 그대로 가져온다. 틀린 조치를 지어낼 수 없게 하려는 것이다."""
    found = None if cause == UNKNOWN else manual.section(db, cause)
    if not found:
        return None
    steps = next((line for line in found["content"].splitlines() if line.startswith("조치:")), "")
    return {"section": found["section"], "source": found["source"], "steps": steps.removeprefix("조치:").strip()}


def write_report(incident, answer, actions):
    lines = [f"원인: {FAULT_NAMES[incident['cause']]} ({incident['basis']})", "", "근거:"]
    lines += [f"- {r}" for r in answer["reasoning"]]
    if answer["doubts"]:
        lines += ["", "의문점:"] + [f"- {d}" for d in answer["doubts"]]
    if actions:
        lines += ["", f"조치 (안내서 [{actions['section']}]):", actions["steps"]]
    return "\n".join(lines)


def run(db, ctx, incident):
    """이미 원인이 정해진 사건의 기록을 LLM이 조회해 설명을 쓴다. Ollama 오류는 호출한 쪽으로 올린다."""
    tools = Tools(db, ctx, incident)
    briefing = _briefing(incident)
    tools.results.append(briefing)   # 사건 시각과 경보 수치를 인용한 것은 출처 없는 수치가 아니다
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": briefing}]

    for _ in range(MAX_STEPS):
        message = _chat(messages, tools=TOOLS)
        calls = message.get("tool_calls") or []
        if not calls:
            break
        messages.append(message)
        for call in calls:
            f = call["function"]
            messages.append({"role": "tool", "name": f["name"], "content": tools.call(f["name"], f.get("arguments") or {})})

    # 함수를 부르지 않았어도 근거 없이 답하지 않도록, 빠진 기본 근거는 코드가 채운다.
    # 노즐 막힘과 온도 센서는 청소 뒤 결과로 갈렸으므로 그 기록도 꼭 보게 한다.
    clog_or_temp = incident["cause"] in ("nozzle_clog", "temp_sensor_drift")
    for name in ("get_readings", "get_defects", "get_alarms", "get_work_history",
                 *(["check_after_clean"] if clog_or_temp else [])):
        if name not in tools.called:
            messages.append({"role": "tool", "name": name, "content": tools.call(name, {})})

    schema = {"type": "object", "required": ["reasoning", "doubts"], "properties": {
        "reasoning": {"type": "array", "items": {"type": "string"}},
        "doubts": {"type": "array", "items": {"type": "string"}},
    }}
    clean_note = "check_after_clean 결과를 근거에 포함한다.\n" if clog_or_temp else ""
    messages.append({"role": "user", "content": ANSWER_PROMPT.format(
        cause=f"{incident['cause']} ({FAULT_NAMES[incident['cause']]})", clean_note=clean_note)})
    reply = json.loads(_chat(messages, format=schema)["content"])

    # LLM이 무엇을 답해도 원인은 코드가 정한 그대로다. 답에서는 설명 두 칸만 꺼낸다.
    answer = {"reasoning": [str(r) for r in reply.get("reasoning") or []],
              "doubts": [str(d) for d in reply.get("doubts") or []]}
    actions = actions_for(db, incident["cause"])
    return {
        **answer,
        "cause": incident["cause"],
        "cause_label": FAULT_NAMES[incident["cause"]],
        "basis": incident["basis"],
        "actions": actions,
        "report": write_report(incident, answer, actions),
        "tools_called": tools.called,
        "manual_sections": tools.manual_sections,
        "unverified_numbers": unverified_numbers(answer["reasoning"] + answer["doubts"], tools.results),
        "other_causes": other_causes_mentioned(answer["reasoning"], incident["cause"]),
        "model": LLM_MODEL,
        "tool_results": tools.results,   # 설명 품질 채점이 "사건 전 A → 사건 중 B"의 순서를 확인할 때 쓴다. 저장하지 않는다
    }
