import type { MachineState } from "../types";

function Gauge({ label, value, max, unit, warnBelow }: {
  label: string;
  value: number;
  max: number;
  unit: string;
  warnBelow?: number;
}) {
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

export function ProductionPanel({ state }: { state: MachineState }) {
  const { OK, NG } = state.counts;
  const total = OK + NG;
  const yieldPct = total ? ((100 * OK) / total).toFixed(2) : "-";
  return (
    <section className="panel">
      <h2>생산 현황</h2>
      <div className="stats">
        <div className="stat">
          <span className="stat-label">생산</span>
          <span className="stat-value">{total.toLocaleString()}</span>
        </div>
        <div className="stat">
          <span className="stat-label">OK</span>
          <span className="stat-value ok">{OK.toLocaleString()}</span>
        </div>
        <div className="stat">
          <span className="stat-label">NG</span>
          <span className="stat-value ng">{NG.toLocaleString()}</span>
        </div>
        <div className="stat">
          <span className="stat-label">수율</span>
          <span className="stat-value">{yieldPct}%</span>
        </div>
      </div>

      <h3>자재 / 버퍼</h3>
      <Gauge
        label="NG 버퍼 여유"
        value={state.ng_buffer_capacity - state.ng_buffer}
        max={state.ng_buffer_capacity}
        unit={`/${state.ng_buffer_capacity}`}
        warnBelow={20}
      />
      <Gauge label="시린지 잔량" value={state.syringe_level_pct} max={100} unit="%" warnBelow={15} />
      <p className="hint">
        시린지 장착 후 {Math.floor(state.syringe_age_min / 60)}시간 {state.syringe_age_min % 60}분 (가사시간 6시간)
      </p>
    </section>
  );
}
