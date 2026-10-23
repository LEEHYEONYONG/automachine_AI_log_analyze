import type { AlarmEntry } from "../types";

export function AlarmBanner({ alarm }: { alarm: AlarmEntry | null }) {
  if (!alarm) return null;
  return (
    <div className="alarm-banner" role="alert">
      <span className="alarm-code">{alarm.code}</span>
      <span className="alarm-unit">{alarm.unit}</span>
      <span className="alarm-text">{alarm.text}</span>
      {alarm.detail && <span className="alarm-detail mono">{alarm.detail}</span>}
      <span className="alarm-time mono">{alarm.set_at.slice(11)}</span>
    </div>
  );
}

export function AlarmHistory({ history }: { history: AlarmEntry[] }) {
  return (
    <section className="panel">
      <h2>알람 이력</h2>
      {history.length === 0 ? (
        <p className="hint">알람 없음</p>
      ) : (
        <div className="table-wrap">
          <table className="alarm-table">
            <thead>
              <tr>
                <th>발생</th>
                <th>해제</th>
                <th>코드</th>
                <th>유닛</th>
                <th>내용</th>
                <th>상세</th>
              </tr>
            </thead>
            <tbody>
              {history.map((a) => (
                <tr key={a.set_at + a.code} className={a.cleared_at ? "" : "active"}>
                  <td className="mono">{a.set_at.slice(11, 19)}</td>
                  <td className="mono">{a.cleared_at ? a.cleared_at.slice(11, 19) : "발생 중"}</td>
                  <td className="mono">{a.code}</td>
                  <td>{a.unit}</td>
                  <td>{a.text}</td>
                  <td className="mono detail">{a.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
