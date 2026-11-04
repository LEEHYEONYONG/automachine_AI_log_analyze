import { tr } from "../../prefs";
import { AlarmHistory } from "../AlarmPanel";
import { ALARM_GUIDE, NG_GUIDE } from "../hmiLabels";

export function AlarmPage({ state }) {
  const active = state.alarm;
  const ngType = active?.code === "E4001" ? /last=(\w+)/.exec(active.detail)?.[1] : undefined;
  const guide = active ? { ...ALARM_GUIDE[active.code], ...(ngType ? NG_GUIDE[ngType] : {}) } : null;

  const counts = new Map();
  for (const a of state.alarm_history) counts.set(a.code, (counts.get(a.code) ?? 0) + 1);
  const frequent = [...counts.entries()].sort((a, b) => b[1] - a[1]);

  return (
    <div className="page">
      <section className={`panel ${active ? "panel-alarm" : ""}`}>
        <h2>{tr("현재 알람")}</h2>
        {!active ? (
          <p className="hint">{tr("발생 중인 알람이 없습니다.")}</p>
        ) : (
          <div className="alarm-guide">
            <div className="alarm-guide-head">
              <span className="alarm-code">{active.code}</span>
              <strong>{guide?.title ?? active.text}</strong>
              <span className="tag">{active.unit}</span>
              <span className="mono muted">{active.set_at}</span>
            </div>
            <dl className="kv">
              <dt>{tr("상세")}</dt>
              <dd className="mono">{active.detail || "-"}</dd>
              {ngType && (
                <>
                  <dt>{tr("불량 유형")}</dt>
                  <dd className="mono">{ngType}</dd>
                </>
              )}
              <dt>{tr("추정 원인")}</dt>
              <dd>{guide?.cause ?? "-"}</dd>
              <dt>{tr("조치 방법")}</dt>
              <dd>{guide?.action ?? "-"}</dd>
            </dl>
            <p className="hint">{tr("조치는 [유지보수] 메뉴에서 장비를 정지한 상태로 진행하고, 끝나면 RESET → START 순서로 재가동합니다.")}</p>
          </div>
        )}
      </section>

      <div className="alarm-grid">
        <AlarmHistory history={state.alarm_history} />
        <section className="panel">
          <h2>{tr("발생 빈도 (최근 20건)")}</h2>
          {frequent.length === 0 ? (
            <p className="hint">{tr("알람 없음")}</p>
          ) : (
            <table className="seq-table">
              <tbody>
                {frequent.map(([code, n]) => (
                  <tr key={code}>
                    <td className="mono">{code}</td>
                    <td>{ALARM_GUIDE[code]?.title ?? code}</td>
                    <td className="mono">{tr("{n}회", { n })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}
