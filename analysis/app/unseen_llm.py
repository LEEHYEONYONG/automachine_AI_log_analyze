"""실험 ①: 규칙이 없는 고장에 LLM이 이름을 붙이는가. 제품 API에서는 쓰지 않는다.

고장 T마다 T의 규칙을 뺀 채 사건을 묶고, 규칙 이름 없이 경비원만 울린 사건 중 T가 진행 중이던 것을 고른다.
같은 사건을 두 조건으로 묻는다.
  A: 고를 수 있는 이름에 T가 있고, 점검 안내서(analysis/manual/*.md, DB)를 찾을 수 있다.
     "안내서에는 있지만 규칙으로는 안 만든 고장".
  B: 이름 목록에서 T를 빼고 '목록에 없음(other)'을 둔다. 안내서 대신 부품 설명서(analysis/manual/devices)를 찾는다.
     other를 고르면 어느 부품의 어떤 문제인지 답한다. "진짜 처음 보는 고장".
대조군: 규칙을 다 둔 채 경비원만 울렸고 진행 중인 고장이 없던 사건. 고장 아님(no_fault)이라고 해야 맞다.

표준 입력: {"periods": {run_id: [{"type", "start", "end"}]}, "fair": train_classifier --fair 답안 (dev만)}
고장 구간은 사건을 고를 때만 쓰고 LLM에게는 보이지 않는다. 채점은 호스트의 eval/explore/unseen_llm_score.py가 한다.

    python -m app.unseen_llm <결과 파일>          # DRY=1이면 LLM 없이 고를 사건만 센다
끊겨도 다시 실행하면 결과 파일에 있는 사건은 건너뛴다.
"""
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

from . import anomaly, classify, foreman, manual
from .database import SessionLocal
from .routes.analysis import rule_candidates

FAULTS = [n for n in foreman.FAULT_NAMES if n not in (foreman.NO_FAULT, foreman.UNKNOWN)]
OTHER = "other"
DEVICE_DIR = manual.MANUAL_DIR / "devices"
COMPONENTS = ["디스펜서 컨트롤러", "시린지 히터", "니들", "시린지", "진공 고정 지그", "공압 조합 유닛", "전자 저울",
              "높이 측정 레이저", "비드 검사 센서", "정렬 비전", "2D 코드 리더", "공압 실린더", "서보 축", "컨베이어"]
PROBLEMS = ["막힘", "끝 오염", "위치 어긋남", "누설·마모", "공급 압력 저하", "센서 치우침", "기포", "설정값 변경",
            "점도 증가", "기타"]
NONE = "해당 없음"

SYSTEM_A = """너는 디스펜싱 장비 라인의 반장이다. 경비원(평소 모습과 다른 값을 찾는 감시)이 울렸지만, 어떤 규칙도 고장 이름을 붙이지 못한 사건이다.
기록을 보고 원인을 고른다. 고장이 아닐 수도 있다.
규칙:
- 먼저 함수를 불러 근거를 모은다. get_readings와 get_defects는 반드시 부른다.
- 고장마다 증상이 어떻게 다른지는 search_manual로 점검 안내서에서 찾는다.
- 주어진 내용과 함수 결과에 없는 수치를 지어내지 않는다.
- 근거로 가를 수 없으면 unknown을 고른다."""

SYSTEM_B = """너는 디스펜싱 장비 라인의 반장이다. 경비원(평소 모습과 다른 값을 찾는 감시)이 울렸지만, 어떤 규칙도 고장 이름을 붙이지 못한 사건이다.
기록을 보고 원인을 고른다. 고장이 아닐 수도 있고, 고를 수 있는 이름 목록에 없는 고장일 수도 있다.
규칙:
- 먼저 함수를 불러 근거를 모은다. get_readings와 get_defects는 반드시 부른다.
- 장비 부품의 동작 원리와 고장 증상은 search_manual로 부품 설명서에서 찾는다.
- 기록이 목록의 어느 고장과도 맞지 않으면 other를 고르고, 부품 설명서를 근거로 어느 부품의 어떤 문제인지 답한다.
- 주어진 내용과 함수 결과에 없는 수치를 지어내지 않는다.
- 근거로 가를 수 없으면 unknown을 고른다."""

ANSWER_A = """지금까지 모은 근거로 판단을 끝내라. JSON으로만 답한다.
cause: 고를 수 있는 이름 하나
confidence: high, medium, low 중 하나
reasoning: 근거 문장 2~4개. 한국어로, 함수 결과의 수치를 그대로 인용한다."""

ANSWER_B = f"""지금까지 모은 근거로 판단을 끝내라. JSON으로만 답한다.
cause: 고를 수 있는 이름 하나. 목록의 어느 고장과도 맞지 않으면 other
component: cause가 other일 때 문제가 있는 부품 ({', '.join(COMPONENTS)}). other가 아니면 {NONE}
problem: cause가 other일 때 그 부품의 문제 ({', '.join(PROBLEMS)}). other가 아니면 {NONE}
confidence: high, medium, low 중 하나
reasoning: 근거 문장 2~4개. 한국어로, 함수 결과의 수치를 그대로 인용한다."""


def tools_for(condition):
    """B에서는 함수 설명에도 고장 이름이 나오지 않게 하고, 설명서 검색이 부품 설명서를 찾는다고 알린다."""
    tools = json.loads(json.dumps(foreman.TOOLS))
    for t in tools:
        f = t["function"]
        if condition == "B" and f["name"] == "check_after_clean":
            f["description"] = "노즐 청소 뒤 비드 폭이 돌아왔는지 본다."
        if condition == "B" and f["name"] == "search_manual":
            f["description"] = "장비 부품 설명서(동작 원리, 사양, 고장 진단표)에서 찾는다."
            f["parameters"]["properties"]["question"]["description"] = "찾을 내용. 예: 진공이 약해지는 원인"
    return tools


class DeviceManual:
    """부품 설명서를 ## 절 단위로 한 번 임베딩해 두고 질문과 가까운 절을 찾는다. DB를 쓰지 않는다."""

    def __init__(self):
        self.sections = []
        for path in sorted(DEVICE_DIR.glob("*.md")):
            for title, body in manual.split_sections(path.read_text(encoding="utf-8")):
                self.sections.append({"source": path.name, "section": title, "content": body})
        self.vectors = manual.embed([f"{s['section']}\n{s['content']}" for s in self.sections])

    def search(self, question, k=manual.TOP_K):
        q = manual.embed([question])[0]

        def cosine(v):
            dot = sum(a * b for a, b in zip(q, v))
            return dot / (math.sqrt(sum(a * a for a in q)) * math.sqrt(sum(b * b for b in v)) or 1)
        ranked = sorted(zip(self.vectors, self.sections), key=lambda x: -cosine(x[0]))
        return [s for _, s in ranked[:k]]


class ExperimentTools(foreman.Tools):
    def __init__(self, db, ctx, incident, devices=None):
        super().__init__(db, ctx, incident)
        self.devices = devices

    def search_manual(self, question=""):
        if self.devices is None:
            return super().search_manual(question)
        hits = self.devices.search(question or "고장 진단")
        self.manual_sections += [h["section"] for h in hits]
        return "\n\n".join(f"[{h['section']}]\n{h['content']}" for h in hits)


def choices(condition, hidden):
    names = [n for n in FAULTS if not (condition == "B" and n == hidden)]
    extra = [OTHER] if condition == "B" else []
    return names + [foreman.NO_FAULT] + extra + [foreman.UNKNOWN]


def briefing(incident, names):
    notes = "\n".join(f"- {n}" for n in incident["notes"])
    labels = ", ".join(f"{n} ({foreman.FAULT_NAMES.get(n, '목록에 없는 고장')})" for n in names)
    return (f"사건 시각: {incident['started_at']:%H:%M:%S} ~ {incident['last_at']:%H:%M:%S}, 경보 {incident['alerts']}개\n"
            f"규칙 의견: 없음\n경비원이 평소와 다르다고 본 값: {', '.join(incident['guard_values'])}\n"
            f"경보가 처음 울렸을 때의 수치:\n{notes}\n고를 수 있는 이름: {labels}")


def schema(condition, names):
    props = {"cause": {"type": "string", "enum": names},
             "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
             "reasoning": {"type": "array", "items": {"type": "string"}}}
    if condition == "B":
        props["component"] = {"type": "string", "enum": COMPONENTS + [NONE]}
        props["problem"] = {"type": "string", "enum": PROBLEMS + [NONE]}
    return {"type": "object", "required": list(props), "properties": props}


def ask(db, ctx, incident, condition, hidden, devices):
    names = choices(condition, hidden)
    tools = ExperimentTools(db, ctx, incident, devices if condition == "B" else None)
    tool_list = tools_for(condition)
    text = briefing(incident, names)
    tools.results.append(text)
    messages = [{"role": "system", "content": SYSTEM_A if condition == "A" else SYSTEM_B},
                {"role": "user", "content": text}]
    for _ in range(foreman.MAX_STEPS):
        message = foreman._chat(messages, tools=tool_list)
        calls = message.get("tool_calls") or []
        if not calls:
            break
        messages.append(message)
        for call in calls:
            f = call["function"]
            messages.append({"role": "tool", "name": f["name"], "content": tools.call(f["name"], f.get("arguments") or {})})

    called_by_model = list(tools.called)
    for name in ("get_readings", "get_defects", "get_alarms", "get_work_history"):
        if name not in tools.called:
            messages.append({"role": "tool", "name": name, "content": tools.call(name, {})})
    messages.append({"role": "user", "content": ANSWER_A if condition == "A" else ANSWER_B})
    reply = json.loads(foreman._chat(messages, format=schema(condition, names))["content"])
    reasoning = [str(r) for r in reply.get("reasoning") or []]
    cause = reply.get("cause") if reply.get("cause") in names else foreman.UNKNOWN
    return {"cause": cause, "component": reply.get("component"), "problem": reply.get("problem"),
            "confidence": reply.get("confidence"), "reasoning": reasoning, "called_by_model": called_by_model,
            "manual_sections": tools.manual_sections,
            "unverified_numbers": foreman.unverified_numbers(reasoning, tools.results)}


def active(periods, at):
    return {p["type"] for p in periods if datetime.fromisoformat(p["start"]) <= at <= datetime.fromisoformat(p["end"])}


def targets(db, run_id, periods, profile):
    """(숨긴 고장 T 또는 None, 사건, ctx) 목록. None은 대조군."""
    ctx = classify.load_context(db, run_id)
    cands = rule_candidates(db, run_id, ctx["recipes"])
    guard = anomaly.detect_anomaly(run_id, ctx["parts"], ctx["sensors"], profile)
    found = []
    for hidden in sorted({p["type"] for p in periods}):
        for incident in foreman.incidents([c for c in cands if c["fault_type"] != hidden], guard):
            if not incident["rule_names"] and hidden in active(periods, incident["started_at"]):
                found.append((hidden, incident))
    for incident in foreman.incidents(cands, guard):
        if not incident["rule_names"] and not active(periods, incident["started_at"]):
            found.append((None, incident))
    return ctx, found


def tree_guess(fair, run_id, incident):
    for c in fair.get(run_id, []):
        if incident["started_at"] <= datetime.fromisoformat(c["detected_at"]) <= incident["last_at"]:
            return c["evidence"]["best_guess"]
    return None


def main():
    out = Path(sys.argv[1])
    dry = os.environ.get("DRY") == "1"
    conditions = os.environ.get("CONDITIONS", "A,B").split(",")
    data = json.load(sys.stdin)
    periods, fair = data["periods"], data.get("fair", {})
    profile = anomaly.load_profile()
    model = None if fair else classify.load_model()     # test: dev로 배운 트리 그대로

    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if not row.get("error"):
                done.add((row["condition"], row["run_id"], row["at"], row["hidden"]))
    devices = None if dry or "B" not in conditions else DeviceManual()

    total = 0
    for run_id, run_periods in periods.items():
        db = SessionLocal()
        try:
            ctx, found = targets(db, run_id, run_periods, profile)
            db.commit()
            pairs = classify.alert_snapshots(ctx, profile) if model else []
            for hidden, incident in found:
                at = incident["started_at"].isoformat()
                if fair:
                    guess = tree_guess(fair, run_id, incident)
                else:
                    first = next((row for alert, row in pairs
                                  if incident["started_at"] <= alert["detected_at"] <= incident["last_at"]), None)
                    guess = classify.predict(model, first)[0] if first else None
                total += 1
                if dry:
                    print(run_id[-6:], at[11:16], hidden or "대조군", "트리", guess, incident["guard_values"], flush=True)
                    continue
                for condition in conditions:
                    if (condition, run_id, at, hidden) in done:
                        continue
                    row = {"condition": condition, "run_id": run_id, "at": at, "hidden": hidden, "tree": guess,
                           "guard_values": incident["guard_values"]}
                    started = time.time()
                    try:
                        row.update(ask(db, ctx, incident, condition, hidden, devices))
                    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
                        row["error"] = f"{type(e).__name__}: {e}"[:200]
                    row["seconds"] = round(time.time() - started, 1)
                    with out.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    print(condition, run_id[-6:], at[11:16], hidden or "대조군", "→", row.get("cause", row.get("error")),
                          row.get("component") or "", row.get("problem") or "", row["seconds"], flush=True)
                    db.rollback()
        finally:
            db.close()
    print(f"사건 {total}개", flush=True)


if __name__ == "__main__":
    main()
