import { tr } from "../../prefs";
import { ProductionPanel } from "../ProductionPanel";
import { TrendPanel } from "../TrendPanel";

const fmt = (s) => {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? tr("{h}시간 {m}분", { h, m }) : tr("{m}분 {s}초", { m, s: Math.round(s % 60) });
};

/** Where the time went since the run started, plus production counters and process trends. */
export function ProductionPage({ state }) {
  const s = state.metrics.seconds;
  const running = s.RUNNING ?? 0;
  const starved = s.STARVED ?? 0;
  const blocked = s.BLOCKED ?? 0;
  const total = running + (s.STOPPED ?? 0) + (s.ALARM ?? 0);
  const rows = [
    { label: tr("생산 가동"), value: running - starved - blocked, note: tr("실제로 제품을 처리한 시간") },
    { label: tr("이전 공정 대기"), value: starved, note: tr("운전 중이지만 투입할 제품이 없던 시간") },
    { label: tr("다음 공정 대기"), value: blocked, note: tr("운전 중이지만 배출할 곳이 없던 시간") },
    { label: tr("정지"), value: s.STOPPED ?? 0, note: tr("휴식, 모델 체인지, 수동 정지") },
    { label: tr("알람"), value: s.ALARM ?? 0, note: tr("알람 발생부터 리셋까지") },
  ];

  return (
    <div className="page">
      <div className="main-grid">
        <ProductionPanel state={state} />
        <section className="panel">
          <h2>{tr("시간 가동 현황 (실행 시작 이후)")}</h2>
          <table className="seq-table">
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}>
                  <td>{r.label}</td>
                  <td className="mono">{fmt(r.value)}</td>
                  <td className="mono">{total ? `${((100 * r.value) / total).toFixed(1)}%` : "-"}</td>
                  <td className="hint">{r.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">{tr("전체 {time}", { time: fmt(total) })}</p>
        </section>
      </div>
      <TrendPanel />
    </div>
  );
}
