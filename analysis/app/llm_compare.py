"""실험용: LLM 모델끼리 원인 판단을 비교한다. 제품은 코드가 원인을 정하므로(foreman.decide) API에서는 쓰지 않는다.
모든 모델이 같은 사건, 같은 지시문, 같은 함수로 답한다. 정답지는 받지 않고, 채점은 호스트의 eval/explore/llm_compare_score.py가 한다.
표준 입력: train_classifier --fair의 답안. 그 런을 빼고 배운 분류 의견을 쓰고, dev 런만 들어온다.

    python -m app.llm_compare <모델> <결과 파일>
끊겨도 다시 실행하면 결과 파일에 있는 사건은 건너뛴다.
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

from . import anomaly, classify, foreman
from .database import SessionLocal
from .routes.analysis import rule_candidates

CAUSES = list(foreman.FAULT_NAMES)

SYSTEM_PROMPT = """너는 디스펜싱 장비 라인의 반장이다. 경보가 울린 사건 하나의 원인을 판단한다.
규칙:
- 먼저 함수를 불러 근거를 모은다. 판단 전에 get_readings와 get_defects는 반드시 부른다.
- 경보 의견은 틀릴 수 있다. 측정값과 작업 기록으로 확인한다.
- 사건 초반에는 값 변화가 작을 수 있다. 변화가 작아도 경보 수치와 맞으면 그 의견을 받아들인다.
- 설정 변경 기록이 표준에서 벗어났으면 레시피 오입력을, 압력과 진공이 함께 나빠졌으면 공장 에어 저하를 먼저 본다.
- check_after_clean은 규칙이나 분류 모델이 노즐 막힘 또는 온도 센서를 말할 때만 부른다.
- 매뉴얼의 '구별' 내용이 궁금하면 search_manual을 부른다.
- 주어진 내용과 함수 결과에 없는 수치를 지어내지 않는다.
- 경보 의견들이 서로 어긋나고 근거로 가를 수 없을 때만 unknown을 고른다."""

ANSWER_PROMPT = f"""지금까지 모은 근거로 판단을 끝내라. JSON으로만 답한다.
cause: 고장 이름 하나 ({', '.join(CAUSES)})
confidence: high, medium, low 중 하나
reasoning: 근거 문장 2~4개. 한국어로, 함수 결과의 수치를 그대로 인용한다."""

SCHEMA = {"type": "object", "required": ["cause", "confidence", "reasoning"], "properties": {
    "cause": {"type": "string", "enum": CAUSES},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "reasoning": {"type": "array", "items": {"type": "string"}},
}}


def fair_guess(answers, incident):
    """이 런을 빼고 배운 트리가 사건 안의 첫 경보에서 낸 의견."""
    for c in answers:
        if incident["started_at"] <= datetime.fromisoformat(c["detected_at"]) <= incident["last_at"]:
            return c["evidence"]["best_guess"]
    return "없음"


def briefing(incident, guess):
    notes = "\n".join(f"- {n}" for n in incident["notes"])
    return (f"사건 시각: {incident['started_at']:%H:%M:%S} ~ {incident['last_at']:%H:%M:%S}, 경보 {incident['alerts']}개\n"
            f"규칙 의견: {', '.join(incident['rule_names']) or '없음'}\n"
            f"경비원이 평소와 다르다고 본 값: {', '.join(incident['guard_values']) or '없음'}\n"
            f"분류 모델 의견: {guess}\n경보가 처음 울렸을 때의 수치:\n{notes}\n"
            f"고를 수 있는 고장 이름: {', '.join(CAUSES)}")


def ask(db, ctx, incident, guess):
    tools = foreman.Tools(db, ctx, incident)
    text = briefing(incident, guess)
    tools.results.append(text)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}]

    for _ in range(foreman.MAX_STEPS):
        message = foreman._chat(messages, tools=foreman.TOOLS)
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

    messages.append({"role": "user", "content": ANSWER_PROMPT})
    reply = json.loads(foreman._chat(messages, format=SCHEMA)["content"])
    cause = reply.get("cause") if reply.get("cause") in CAUSES else classify.UNKNOWN
    reasoning = [str(r) for r in reply.get("reasoning") or []]
    return {"cause": cause, "confidence": reply.get("confidence"), "reasoning": reasoning,
            "called_by_model": called_by_model,
            "unverified_numbers": foreman.unverified_numbers(reasoning, tools.results)}


def main():
    model, out = sys.argv[1], Path(sys.argv[2])
    limit = int(os.environ.get("LIMIT", 0))
    foreman.LLM_MODEL = model
    fair = json.load(sys.stdin)
    profile = anomaly.load_profile()

    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if not row.get("error"):       # 오류가 난 사건은 다시 돌린다
                done.add((row["run_id"], row["at"]))

    count = 0
    for run_id, answers in fair.items():
        db = SessionLocal()
        try:
            ctx = classify.load_context(db, run_id)
            guard = anomaly.detect_anomaly(run_id, ctx["parts"], ctx["sensors"], profile)
            found = foreman.incidents(rule_candidates(db, run_id, ctx["recipes"]), guard)
            db.commit()
            for incident in found:
                at = incident["started_at"].isoformat()
                if (run_id, at) in done:
                    continue
                if limit and count >= limit:
                    return
                count += 1
                guess = fair_guess(answers, incident)
                row = {"model": model, "run_id": run_id, "at": at, "tree": guess,
                       "rule": incident["rule_names"][0] if incident["rule_names"] else None}
                started = time.time()
                try:
                    row.update(ask(db, ctx, incident, guess))
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
                    row["error"] = f"{type(e).__name__}: {e}"[:200]
                row["seconds"] = round(time.time() - started, 1)
                with out.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(run_id[-6:], at[11:16], row.get("cause", row.get("error")), row["seconds"], flush=True)
                db.rollback()
        finally:
            db.close()


if __name__ == "__main__":
    main()
