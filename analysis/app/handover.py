"""교대 인수인계 요약. 코드가 교대 동안의 사실을 모으고, LLM은 그 사실로 다음 조에게 넘길 글을 쓴다.
판단은 하지 않는다. 고장 원인은 코드가 정한 것(foreman.judge)을 그대로 옮긴다.
글은 코드가 검사한다: 사실마다 꼭 들어갈 낱말이 한 문장 안에 있는지(빠짐), 사실에 없는 수치·알람 코드·시각이 있는지(지어냄).

    python -m app.handover <결과 파일>     # 실험: 표준 입력의 런 목록을 교대마다 요약하고 검사한다
"""
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, time as clock, timedelta
from pathlib import Path

import httpx
from sqlalchemy import text

from . import anomaly, classify, foreman
from .database import SessionLocal

SHIFT_STARTS = (clock(8, 0), clock(20, 0))     # config/machine.json plant.shifts
OPEN_MIN = 30                                   # 교대 끝 30분 안에도 경보가 있으면 다음 조가 이어 볼 일이다

ACTION_LABEL = {
    "empty_ng_buffer": "NG 버퍼 비우기", "remove_part": "제품 제거", "vision_check": "비전 점검",
    "vacuum_check": "진공 점검", "replace_vacuum_pad": "진공 패드 교체", "nozzle_clean": "노즐 청소",
    "purge": "퍼지", "needle_calibration": "니들 위치 교정", "replace_syringe": "시린지 교체",
    "air_check": "에어 공급 확인", "call_engineer": "엔지니어 점검", "model_change": "모델 체인지",
}
NG_LABEL = {
    "BEAD_BREAK": "비드 끊김", "BEAD_VOID": "비드 빈 곳", "STRINGING": "실 끌림", "WIDTH_LOW": "폭 미달",
    "WIDTH_HIGH": "폭 초과", "BEAD_OFFSET": "위치 벗어남", "PARTICLE": "이물", "INIT_INCOMPLETE": "원점 복귀 중 도포 중단",
    "SCRAP_E1001": "코드 읽기 실패로 제거", "SCRAP_E2001": "정렬 마크 없음으로 제거",
    "SCRAP_E2002": "정렬 위치 초과로 제거", "SCRAP_INIT": "원점 복귀 때 제거",
}
RUN_MODE_LABEL = {"PRODUCTION": "자동 운전", "DRY": "드라이 런", "DUMMY": "더미 런"}
# simulator/settings.py SPEC labels (the analysis image does not include the simulator)
SETTING_LABEL = {
    "lot_size": "로트 크기", "production_target": "생산 목표 (0이면 끔)", "weight_check_interval": "중량 검사 주기",
    "vacuum_threshold_kpa": "진공 판정 기준", "max_vacuum_retries": "진공 재시도", "temp_alarm_band_c": "온도 감시 폭 (±)",
    "syringe_low_pct": "시린지 잔량 경고", "pot_life_h": "가사 시간", "vision_score_threshold": "정렬 점수 기준",
    "vision_max_offset_mm": "정렬 허용 위치 차", "bead_max_offset_mm": "비드 위치 허용", "max_consecutive_ng": "연속 불량 정지 수",
    "auto_logout_min": "자동 로그아웃",
}
DUMMY_LOT = "DUMMY"
PARAM_LABEL = {
    "dispense_pressure_kpa": "토출 압력", "dispense_time_s": "토출 시간", "retract_delay_s": "토출 후 대기",
    "syringe_temp_c": "시린지 온도", "nozzle_height_mm": "도포 갭",
}

def shifts(start, end):
    """[start, end]를 교대 경계에서 자른 (교대 시작, 구간 시작, 구간 끝) 목록."""
    out = []
    day = datetime.combine(start.date() - timedelta(days=1), clock(0))
    bounds = sorted(datetime.combine(day.date() + timedelta(days=d), s) for d in range(4) for s in SHIFT_STARTS)
    for a, b in zip(bounds, bounds[1:]):
        lo, hi = max(a, start), min(b, end)
        if lo < hi:
            out.append((a, lo, hi))
    return out


def _hm(ts):
    return f"{ts:%H:%M}"


def facts(ctx, alarms, incidents, lo, hi):
    """교대 동안의 사실. {text: 글에 넣을 문장, need: 한 문장 안에 있어야 할 낱말들}"""
    out = []
    inside = [i for i in incidents if lo <= i["started_at"] < hi or (i["started_at"] < lo <= i["last_at"])]
    for i in inside:
        label = foreman.FAULT_NAMES[i["cause"]]
        still = hi - i["last_at"] <= timedelta(minutes=OPEN_MIN)
        tail = " 교대 끝까지 경보가 이어져 다음 조가 확인해야 한다." if still else ""
        out.append({"text": f"AI 경보: {_hm(max(i['started_at'], lo))}부터 {label} 의심 (코드 판단).{tail}",
                    "need": [label, _hm(max(i["started_at"], lo))], "open": still})

    codes = Counter(a["code"] for a in alarms if lo <= a["set_ts"] < hi)
    for code, n in sorted(codes.items()):
        times = [_hm(a["set_ts"]) for a in alarms if a["code"] == code and lo <= a["set_ts"] < hi]
        message = next(a["message"] for a in alarms if a["code"] == code)
        shown = ", ".join(times[:3]) + (" 등" if n > 3 else "")
        out.append({"text": f"알람 {code} {message} {n}회 ({shown}).", "need": [code, f"{n}회"]})

    actions = Counter(m["action"] for m in ctx["maintenance"] if lo <= m["ts"] < hi)
    for action, n in sorted(actions.items()):
        label = ACTION_LABEL.get(action, action)
        out.append({"text": f"정비: {label} {n}회.", "need": [label, f"{n}회"]})

    for c in ctx["changes"]:
        if lo <= c["ts"] < hi:
            v = c["attrs"]
            label = PARAM_LABEL.get(v["param"], v["param"])
            standard = ctx["recipes"].get(v["recipe"], {}).get(v["param"])
            out.append({"text": f"설정 변경: {_hm(c['ts'])} {label} {v['old']} → {v['new']} (표준 {standard}).",
                        "need": [label, str(v["new"])]})

    for e in ctx.get("machine_events", []):
        if not lo <= e["ts"] < hi:
            continue
        v = e["attrs"]
        if e["message"].startswith("Setting changed"):
            label = SETTING_LABEL.get(v.get("param"), v.get("param"))
            out.append({"text": f"장비 설정 변경: {_hm(e['ts'])} {label} {v.get('old')} → {v.get('new')}.",
                        "need": [label, str(v.get("new"))]})
        elif e["message"].startswith("Run mode change"):
            label = RUN_MODE_LABEL.get(v.get("run_mode"), v.get("run_mode"))
            out.append({"text": f"운전 방식 변경: {_hm(e['ts'])} {label}.", "need": [label]})

    in_shift = [p for p in ctx["parts"] if lo <= p["start_time"] < hi]
    dummies = [p for p in in_shift if p.get("lot_id") == DUMMY_LOT]
    parts = [p for p in in_shift if p.get("lot_id") != DUMMY_LOT]
    if dummies:
        out.append({"text": f"더미 런: 더미 제품 {len(dummies)}개 (생산 수 제외).", "need": ["더미", f"{len(dummies)}개"]})
    ng = Counter(p["ng_reason"] for p in parts if p["ng_reason"])
    total_ng = sum(ng.values())
    out.append({"text": f"생산: {len(parts)}개, 그중 불량 {total_ng}개.", "need": [str(len(parts)), str(total_ng)]})
    for reason, n in ng.most_common(3):
        label = NG_LABEL.get(reason, reason)
        out.append({"text": f"불량 사유: {label} {n}개.", "need": [label, f"{n}개"]})
    return out


def template(items):
    """코드만으로 쓴 인수인계. 빠짐과 지어냄이 없는 기준선이다."""
    items = sorted(items, key=lambda f: not f.get("open"))
    return "\n".join(f"- {f['text']}" for f in items)


SUMMARY_PROMPT = """너는 디스펜싱 장비 라인의 반장이다. 교대가 끝나 다음 조에게 넘길 인수인계의 맨 위 요약을 쓴다.
전체 기록 목록은 따로 붙으므로, 너는 다음 조가 가장 먼저 알아야 할 것만 고른다.
규칙:
- summary: 이번 교대의 핵심 1~3문장. [이어 볼 일]이 있으면 첫 문장에 쓴다. 그다음 AI 경보, 그다음 자주 난 알람.
- todo: 다음 조가 할 일 0~2문장. [이어 볼 일]이 있으면 그것을 확인하라고 쓴다. 없으면 빈 목록.
- 주어진 사실만 쓴다. 사실에 없는 수치, 알람 코드, 시각, 원인을 지어내지 않는다.
- 원인 이름과 알람 코드는 주어진 글자 그대로 쓴다. JSON으로만 답한다."""

SUMMARY_SCHEMA = {"type": "object", "required": ["summary", "todo"], "properties": {
    "summary": {"type": "array", "items": {"type": "string"}},
    "todo": {"type": "array", "items": {"type": "string"}},
}}


def priorities(items):
    """요약에 꼭 들어가야 할 사실: 이어 볼 일, 그다음 가장 최근 AI 경보 2개. AI 경보가 없으면 가장 잦은 알람."""
    opened = [f for f in items if f.get("open")]
    ai = [f for f in items if f["text"].startswith("AI 경보") and not f.get("open")]
    room = max(0, 2 - len(opened))
    must = opened + (ai[-room:] if room else [])
    if not must:
        alarms = [f for f in items if f["text"].startswith("알람")]
        if alarms:
            must = [max(alarms, key=lambda f: int(f["need"][1].removesuffix("회")))]
    return [{"text": f["text"], "need": f["need"][:1]} for f in must]     # 요약은 이름만 맞으면 된다


def summarize(shift_start, lo, hi, items):
    numbered = "\n".join(f"{n}. {'[이어 볼 일] ' if f.get('open') else ''}{f['text']}" for n, f in enumerate(items, 1))
    user = (f"교대: {shift_start:%m-%d %H:%M} 시작 조, 기록 구간 {_hm(lo)}~{_hm(hi)}\n"
            f"사실 {len(items)}개:\n{numbered}")
    reply = json.loads(foreman._chat([{"role": "system", "content": SUMMARY_PROMPT}, {"role": "user", "content": user}],
                                     format=SUMMARY_SCHEMA)["content"])
    return [str(s) for s in reply.get("summary") or []], [str(s) for s in reply.get("todo") or []], user


def handover_text(summary, todo, items):
    """다음 조에게 보여 줄 글: LLM 요약과 할 일, 그 아래 코드가 만든 전체 목록."""
    lines = ["[요약]"] + [f"- {s}" for s in summary]
    if todo:
        lines += ["[다음 조 할 일]"] + [f"- {s}" for s in todo]
    return "\n".join(lines + ["[전체 기록]", template(items)])


SENTENCE = re.compile(r"[^\n.!?]+")
# 한글이 바로 붙어도("10:14부터") 잡히도록 \b 대신 숫자·글자 경계를 직접 본다
CODE = re.compile(r"(?<![A-Za-z0-9])E\d{4}(?!\d)")
HHMM = re.compile(r"(?<!\d)\d{1,2}:\d{2}(?!\d)")


def check(body, items, source):
    """빠진 사실, 사실에 없는 수치·알람 코드·시각. 처음 시험(11/4)은 LLM이 전문을 썼고, 지금은 요약만 쓴다."""
    sentences = [s.strip() for s in body.splitlines() if s.strip()]
    pieces = sentences + [p.strip() for s in sentences for p in SENTENCE.findall(s)]
    missing = [f["text"] for f in items if not any(all(w in p for w in f["need"]) for p in pieces)]
    known = "\n".join(f["text"] for f in items) + "\n" + source
    return {
        "missing": missing,
        "made_up_numbers": foreman.unverified_numbers(sentences, [known]),
        "made_up_codes": sorted(set(CODE.findall(body)) - set(CODE.findall(known))),
        "made_up_times": sorted(set(HHMM.findall(body)) - set(HHMM.findall(known))),
    }


MIN_SHIFT = timedelta(hours=1)     # 1시간이 안 되는 자투리 교대는 넘기지 않는다


def load_alarms(db, run_id):
    return db.execute(text("SELECT code, set_ts, message, detail FROM alarms WHERE run_id = :r ORDER BY set_ts"),
                      {"r": run_id}).mappings().all()


def load(db, run_id, profile, model):
    from .routes.analysis import rule_candidates    # routes가 이 모듈을 쓰므로 여기서 읽는다
    ctx = classify.load_context(db, run_id)
    found = foreman.judge(ctx, rule_candidates(db, run_id, ctx["recipes"]), profile, model)
    return ctx, load_alarms(db, run_id), found


def shift_list(ctx, alarms, incidents):
    """런의 교대마다 (교대 시작, 구간 시작, 구간 끝, 사실 목록). API와 실험이 같은 함수를 쓴다."""
    if not ctx["parts"]:
        return []
    out = []
    for shift_start, lo, hi in shifts(ctx["parts"][0]["start_time"], ctx["parts"][-1]["start_time"]):
        if hi - lo >= MIN_SHIFT:
            out.append((shift_start, lo, hi, facts(ctx, alarms, incidents, lo, hi)))
    return out


def write_summary(shift_start, lo, hi, items):
    """LLM 요약과 코드의 검사 결과. 제품 API가 쓴다."""
    summary, todo, source = summarize(shift_start, lo, hi, items)
    must = priorities(items)
    return {"summary": summary, "todo": todo, "must": [f["text"] for f in must],
            **check("\n".join(summary + todo), must, source), "model": foreman.LLM_MODEL}


def main():
    out = Path(sys.argv[1])
    run_ids = json.load(sys.stdin)
    profile, model = anomaly.load_profile(), classify.load_model()
    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if not row.get("error"):
                done.add((row["run_id"], row["shift"]))
    for run_id in run_ids:
        db = SessionLocal()
        try:
            ctx, alarms, found = load(db, run_id, profile, model)
            db.commit()
            for shift_start, lo, hi, items in shift_list(ctx, alarms, found):
                if (run_id, shift_start.isoformat()) in done:
                    continue
                must = priorities(items)
                row = {"run_id": run_id, "shift": shift_start.isoformat(), "facts": [f["text"] for f in items],
                       "must": [f["text"] for f in must], "has_open": any(f.get("open") for f in items)}
                started = time.time()
                try:
                    summary, todo, source = summarize(shift_start, lo, hi, items)
                    result = check("\n".join(summary + todo), must, source)
                    row.update({"summary": summary, "todo": todo, **result,
                                "open_first": not row["has_open"] or any(
                                    f["need"][0] in (summary[0] if summary else "") for f in items if f.get("open")),
                                "too_long": len(summary) > 3 or len(todo) > 2,
                                "handover": handover_text(summary, todo, items)})
                except (httpx.HTTPError, ValueError, KeyError) as e:
                    row["error"] = f"{type(e).__name__}: {e}"[:200]
                row["seconds"] = round(time.time() - started, 1)
                with out.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(run_id[-6:], shift_start.strftime("%m-%d %H"), "꼭 담을 것", len(must), "빠짐", len(row.get("missing", [])),
                      "지어냄", len(row.get("made_up_numbers", [])) + len(row.get("made_up_codes", [])) + len(row.get("made_up_times", [])),
                      row["seconds"], flush=True)
        finally:
            db.close()


if __name__ == "__main__":
    main()
