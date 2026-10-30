#!/bin/bash
# 규칙 2 오탐 재현 (2026-10-30): dev 공기 부족 런에서 기계가 더 오래 멈췄다고 치고 옛 규칙(60분 기억)과 지금 규칙을 비교
# 멈춘 동안 20샘플 창에 옛 값이 남아 재시작 직후 "진공 약함 + 압력 정상"처럼 보인다. 재시작 시점을 N분 뒤로 민다
# test 런(498361)은 읽지 않는다. 실제 시뮬레이션이 아니라 dev 기록을 시간만 밀어 재생한 것
cd ~/projects/automachine_AI_log_analyze || exit 1
docker compose exec -T analysis python - <<'EOF'
import statistics
from datetime import timedelta
from sqlalchemy import text
from app import rules
from app.database import SessionLocal

AIR = ["20261028_0800_aba133", "20261028_0800_df12b1", "20261030_0800_8da1cd", "20261030_0800_e84c24"]
MEMORY = timedelta(minutes=60)
db = SessionLocal()

def load(run):
    return [dict(x) for x in db.execute(text("""
        SELECT ts, mode, disp_valve_open, disp_pressure_kpa, fixture_vac_kpa FROM sensor_trend
        WHERE run_id=:r ORDER BY ts"""), {"r": run}).mappings().all()]

def old_rule(samples, memory=MEMORY):
    """고치기 전 규칙 2: 급락 뒤 memory 동안만 무시한다."""
    fires, window, past, last_sudden, on = [], [], [], None, False
    for s in samples:
        if s["mode"] != "RUNNING" or s["disp_valve_open"] != 1:
            continue
        window.append(s)
        if len(window) > rules.LEAK_WINDOW:
            window.pop(0)
        if len(window) < rules.LEAK_WINDOW:
            continue
        ts = s["ts"]
        vac = statistics.median(x["fixture_vac_kpa"] for x in window)
        pres = statistics.median(x["disp_pressure_kpa"] for x in window)
        past.append((ts, vac))
        while len(past) >= 2 and past[1][0] <= ts - rules.LEAK_DROP_LOOK:
            past.pop(0)
        if past[0][0] <= ts - rules.LEAK_DROP_LOOK and vac - past[0][1] >= rules.LEAK_DROP:
            last_sudden = ts
        recent = last_sudden is not None and ts - last_sudden <= memory
        hit = vac > rules.LEAK_VACUUM_MIN and pres >= rules.LEAK_PRESSURE_MIN and not recent
        if hit and not on:
            fires.append(ts)
        on = hit
    return fires

def clock(times):
    return ",".join(t.strftime("%H:%M") for t in times) or "-"

print(f"{'런':<8}{'+분':>4}  {'옛 규칙(60분 기억)':<20}지금 규칙")
for run in AIR:
    rows = load(run)
    cut = old_rule(rows, memory=timedelta(0))[-1]     # 기억이 없었다면 마지막으로 울렸을 샘플
    for extra in (0, 15, 30, 45, 60, 90):
        moved = [{**s, "ts": s["ts"] + timedelta(minutes=extra)} if s["ts"] >= cut else s for s in rows]
        now = [c["detected_at"] for c in rules.detect_vacuum_leak(run, moved)]
        print(f"{run[-6:]:<8}{extra:>4}  {clock(old_rule(moved)):<20}{clock(now)}")
EOF
