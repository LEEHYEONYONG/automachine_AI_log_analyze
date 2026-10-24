import { STATION_LABEL } from "../labels";

/** Most recent INFO/WARN/ALARM events, newest on top. */
export function LiveLog({ entries, onMore }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>실시간 로그</h2>
        {onMore && (
          <button className="link" onClick={onMore}>
            전체 로그 보기
          </button>
        )}
      </div>
      <div className="log-box" role="log" aria-live="polite">
        {entries.length === 0 && <p className="hint">로그 없음</p>}
        {entries.map((e, i) => (
          <div key={`${e.ts}-${i}`} className={`log-line lv-${e.level}`}>
            <span className="mono log-ts">{e.ts.slice(11, 19)}</span>
            <span className="log-level">{e.level}</span>
            <span className="log-unit">{STATION_LABEL[e.unit] ?? e.unit}</span>
            <span className="mono log-text">{e.text}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
