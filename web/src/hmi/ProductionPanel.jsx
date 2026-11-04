import { useT } from "../prefs";

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
  const t = useT();
  const { OK, NG } = state.counts;
  const target = state.production_target;
  const total = OK + NG;
  const { uph, tact_s } = state.metrics;
  return (
    <section className="panel">
      <h2>{t("생산 현황")}</h2>
      {state.run.mode !== "PRODUCTION" && (
        <p className="notice notice-warn">
          {state.run.mode === "DRY"
            ? t("드라이 런 중입니다. 제품 없이 동작만 확인하며 생산 수에 넣지 않습니다 (사이클 {n}회).", { n: state.run.dry_cycles })
            : t("더미 런 중입니다. 더미 {fed}/{count}개, 트레이 {tray}개. 생산 수에 넣지 않습니다.", { fed: state.run.dummy_fed, count: state.run.dummy_count, tray: state.run.dummy_tray })}
        </p>
      )}
      <div className="stats stats-3">
        <Stat label={t("생산")} value={total.toLocaleString()} />
        <Stat label="OK" value={OK.toLocaleString()} tone="ok" />
        <Stat label="NG" value={NG.toLocaleString()} tone="ng" />
        <Stat label={t("수율")} value={total ? `${((100 * OK) / total).toFixed(2)}%` : "-"} />
        <Stat label={t("UPH (최근 1시간)")} value={uph.toLocaleString()} />
        <Stat label={t("택트 타임")} value={tact_s ? t("{s}초", { s: tact_s.toFixed(1) }) : "-"} />
      </div>

      {target > 0 && (
        <Gauge label={t("생산 목표 (OK 기준)")} value={OK} max={target} unit={`/${target.toLocaleString()}`} />
      )}

      <h3>{t("자재 / 버퍼")}</h3>
      <Gauge label={t("시린지 잔량")} value={state.syringe_level_pct} max={100} unit="%" warnBelow={15} />
      <p className="hint">
        {t("시린지 장착 후 {h}시간 {m}분 (가사시간 {limit}시간)", { h: Math.floor(state.syringe_age_min / 60), m: state.syringe_age_min % 60, limit: state.pot_life_h })}
      </p>
      <Gauge
        label={t("NG 버퍼 여유")}
        value={state.ng_buffer_capacity - state.ng_buffer}
        max={state.ng_buffer_capacity}
        unit={`/${state.ng_buffer_capacity}`}
        warnBelow={20}
      />
    </section>
  );
}
