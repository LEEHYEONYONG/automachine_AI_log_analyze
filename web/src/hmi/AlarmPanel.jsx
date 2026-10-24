import { ALARM_GUIDE } from "./hmiLabels";

/** Red bar on every HMI screen while an alarm is active; clicking it opens the alarm screen. */
export function AlarmBanner({ alarm, onClick }) {
  if (!alarm) return null;
  return (
    <button className="alarm-banner" role="alert" onClick={onClick} title="알람 화면에서 조치 방법 보기">
      <span className="alarm-code">{alarm.code}</span>
      <span className="alarm-unit">{alarm.unit}</span>
      <span className="alarm-text">{ALARM_GUIDE[alarm.code]?.title ?? alarm.text}</span>
      {alarm.detail && <span className="alarm-detail mono">{alarm.detail}</span>}
      <span className="alarm-time mono">{alarm.set_at.slice(11)}</span>
    </button>
  );
}

const duration = (a) => {
  if (!a.cleared_at) return "발생 중";
  const s = Math.round((Date.parse(a.cleared_at.replace(" ", "T")) - Date.parse(a.set_at.replace(" ", "T"))) / 1000);
  return s >= 60 ? `${Math.floor(s / 60)}분 ${s % 60}초` : `${s}초`;
};

export function AlarmHistory({ history }) {
  return (
    <section className="panel">
      <h2>알람 이력 (최근 20건)</h2>
      {history.length === 0 ? (
        <p className="hint">알람 없음</p>
      ) : (
        <div className="table-wrap">
          <table className="alarm-table">
            <thead>
              <tr>
                <th>발생</th>
                <th>해제</th>
                <th>정지 시간</th>
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
                  <td className="mono">{a.cleared_at ? a.cleared_at.slice(11, 19) : "-"}</td>
                  <td className="mono">{duration(a)}</td>
                  <td className="mono">{a.code}</td>
                  <td>{a.unit}</td>
                  <td>{ALARM_GUIDE[a.code]?.title ?? a.text}</td>
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
