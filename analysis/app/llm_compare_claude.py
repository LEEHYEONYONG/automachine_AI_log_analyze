"""실험용: llm_compare와 같은 사건·지시문·함수를 Claude API로 돌린다. 제품은 로컬 모델만 쓰며, 이 파일은 비교에만 쓴다.
anthropic 패키지는 이미지에 넣지 않고 eval/explore/llm_compare.sh가 실행할 때만 설치한다. 키는 ANTHROPIC_API_KEY 환경 변수로 받는다.
"""
import json

import anthropic

from . import foreman
from .llm_compare import ANSWER_PROMPT, SCHEMA, SYSTEM_PROMPT, briefing
from .classify import UNKNOWN

EFFORT = "high"
PRICES = {"claude-opus-5-5": {"input": 4.0, "cache_write": 5.0, "cache_read": 0.2, "output": 20.0}}  # 100만 토큰당 달러
TOOLS = [{"name": t["function"]["name"], "description": t["function"]["description"],
          "input_schema": {**t["function"]["parameters"], "additionalProperties": False}} for t in foreman.TOOLS]
FORMAT = {"type": "json_schema", "schema": {**SCHEMA, "additionalProperties": False}}

client = anthropic.Anthropic(max_retries=4)


def _text(content):
    return next(b.text for b in content if b.type == "text")


def ask(db, ctx, incident, guess, model):
    prices = PRICES[model]
    usage = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    served_by = set()

    def call(messages, **extra):
        try:
            response = client.beta.messages.create(
                model=model, max_tokens=16000, system=SYSTEM_PROMPT, tools=TOOLS, messages=messages,
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **extra)
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as e:
            raise ValueError(type(e).__name__) from None   # 이 사건만 오류로 남기고 넘어간다. 키·결제 오류는 전체를 멈춘다
        usage["input"] += response.usage.input_tokens
        usage["cache_write"] += response.usage.cache_creation_input_tokens or 0
        usage["cache_read"] += response.usage.cache_read_input_tokens or 0
        usage["output"] += response.usage.output_tokens
        served_by.add(response.model)
        if response.stop_reason == "refusal":
            raise ValueError("refusal")
        return response

    tools = foreman.Tools(db, ctx, incident)
    text = briefing(incident, guess)
    tools.results.append(text)
    messages = [{"role": "user", "content": text}]
    effort = {"effort": EFFORT}

    for _ in range(foreman.MAX_STEPS):
        response = call(messages, output_config=effort)
        messages.append({"role": "assistant", "content": response.content})
        calls = [b for b in response.content if b.type == "tool_use"]
        if not calls:
            break
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c.id, "content": tools.call(c.name, c.input or {})} for c in calls]})

    called_by_model = list(tools.called)
    # 로컬 모델 실험과 똑같이, 부르지 않은 기본 자료는 코드가 채운 뒤 답을 받는다.
    filled = [f"[{name}]\n{tools.call(name, {})}" for name in
              ("get_readings", "get_defects", "get_alarms", "get_work_history") if name not in tools.called]
    closing = {"type": "text", "text": "\n\n".join(filled + [ANSWER_PROMPT])}
    if messages[-1]["role"] == "user":
        messages[-1]["content"].append(closing)
    else:
        messages.append({"role": "user", "content": [closing]})
    final = call(messages, tool_choice={"type": "none"}, output_config={**effort, "format": FORMAT})
    reply = json.loads(_text(final.content))

    cause = reply.get("cause") if reply.get("cause") in SCHEMA["properties"]["cause"]["enum"] else UNKNOWN
    reasoning = [str(r) for r in reply.get("reasoning") or []]
    cost = sum(usage[k] * prices[k] for k in usage) / 1_000_000
    return {"cause": cause, "confidence": reply.get("confidence"), "reasoning": reasoning,
            "called_by_model": called_by_model,
            "unverified_numbers": foreman.unverified_numbers(reasoning, tools.results),
            "usage": usage, "cost_usd": round(cost, 5), "served_by": sorted(served_by)}
