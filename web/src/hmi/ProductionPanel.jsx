function Gauge({ label, value, max, unit, warnBelow }

) {
  const pct = Math.max(0, Math.min(100, (100 * value) / max));
  const warn = warnBelow !== undefined && pct < warnBelow;
  return (
    <div className="gauge">
      <div className="gauge-head">
        <span>{label}</span>
        <span className="mono">
          {value}
          {unit}
        </span>
      </div>
      <div className="gauge-track">
        <div className={`gauge-fill ${warn ? "warn" : ""}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className={`stat-value ${tone ?? ""}`}>{value}</span>
    </div>
  );
}

export function ProductionPanel({ state }) {
  const { OK, NG } = state.counts;
  const total = OK + NG;
  const { uph, tact_s } = state.metrics;
  return (
    <section className="panel">
      <h2>생산 현황</h2>
      <div className="stats stats-3">
        <Stat label="생산" value={total.toLocaleString()} />
        <Stat label="OK" value={OK.toLocaleString()} tone="ok" />
        <Stat label="NG" value={NG.toLocaleString()} tone="ng" />
        <Stat label="수율" value={total ? `${((100 * OK) / total).toFixed(2)}%` : "-"} />
        <Stat label="UPH (최근 1시간)" value={uph.toLocaleString()} />
        <Stat label="택트 타임" value={tact_s ? `${tact_s.toFixed(1)}초` : "-"} />
      </div>

      <h3>자재 / 버퍼</h3>
      <Gauge label="시린지 잔량" value={state.syringe_level_pct} max={100} unit="%" warnBelow={15} />
      <p className="hint">
        시린지 장착 후 {Math.floor(state.syringe_age_min / 60)}시간 {state.syringe_age_min % 60}분 (가사시간 6시간)
      </p>
      <Gauge
        label="NG 버퍼 여유"
        value={state.ng_buffer_capacity - state.ng_buffer}
        max={state.ng_buffer_capacity}
        unit={`/${state.ng_buffer_capacity}`}
        warnBelow={20}
      />
    </section>
  );
}
