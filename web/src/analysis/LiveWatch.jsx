import { Fragment, useState } from "react";
import { evidenceText, time } from "./evidence";
import { Report } from "./Report";
import { useWatch } from "./useWatch";

const API = "/api/analysis";

/** Loads the run as it is now, then asks the foreman. The run must be in the DB for the report's tools. */
async function writeLiveReport(runId, at) {
  const fail = async (res, what) => {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${what} (${res.status})`);
  };
  const loaded = await fetch(`${API}/runs/${runId}/ingest`, { method: "POST" });
  if (!loaded.ok) await fail(loaded, "지금 런을 적재하지 못했습니다");
  const res = await fetch(`${API}/runs/${runId}/incidents/report?at=${encodeURIComponent(at)}`, { method: "POST" });
  if (!res.ok) await fail(res, "보고서를 쓰지 못했습니다");
  return res.json();
}

function leadText(alert) {
  if (!alert.first_alarm) return "관련 설비 알람 아직 없음";
  const lead = alert.lead_min;
  return lead >= 0
    ? `설비 알람 ${alert.first_alarm.code}보다 ${Math.round(lead)}분 먼저`
    : `설비 알람 ${alert.first_alarm.code}보다 ${Math.round(-lead)}분 늦게`;
}

function evidenceLine(alert) {
  return alert.evidence ? evidenceText(alert.evidence.type, alert.evidence.data) : alert.basis;
}

/** A strip under the header on every tab. Shows the newest AI alert until it is dismissed or a newer one arrives. */
export function LiveAlertBar({ onOpen }) {
  const watch = useWatch();
  const [hidden, setHidden] = useState(null);
  const alerts = watch?.alerts ?? [];
  const newest = alerts.at(-1);
  if (!newest || hidden === `${watch.run_id}/${newest.started_at}`) return null;
  return (
    <div className="live-bar" role="status">
      <button className="live-bar-main" onClick={onOpen} title="AI 분석 탭에서 경보 목록 보기">
        <span className="live-bar-tag">AI 예측 경보</span>
        <span className="mono">{time(newest.started_at)}</span>
        <strong>{newest.cause_label}</strong>
        <span className="live-bar-evidence">{evidenceLine(newest)}</span>
        <span className="live-bar-lead">{leadText(newest)}</span>
        {alerts.length > 1 && <span className="muted small">외 {alerts.length - 1}건</span>}
      </button>
      <button className="btn-text" aria-label="경보 숨기기" onClick={() => setHidden(`${watch.run_id}/${newest.started_at}`)}>
        ✕
      </button>
    </div>
  );
}

/** The full list for the current run, at the top of the analysis tab. */
export function LivePanel() {
  const watch = useWatch();
  const [reports, setReports] = useState({});
  const [writing, setWriting] = useState(null);
  const [error, setError] = useState(null);

  const write = async (at) => {
    setWriting(at);
    setError(null);
    try {
      const report = await writeLiveReport(watch.run_id, at);
      setReports((r) => ({ ...r, [`${watch.run_id}/${at}`]: report }));
    } catch (e) {
      setError(e.message);
    } finally {
      setWriting(null);
    }
  };

  if (!watch) {
    return (
      <section className="panel">
        <h2>실시간 감시</h2>
        <p className="hint">실시간 감시에 연결하지 못했습니다. k8s에서만 동작합니다.</p>
      </section>
    );
  }
  const alerts = [...watch.alerts].reverse();
  return (
    <section className="panel">
      <h2>
        실시간 감시 · <span className="mono">{watch.run_id ?? "-"}</span>
      </h2>
      <p className="hint">
        지금 돌고 있는 런의 기록을 몇 초마다 이어 읽어 규칙, 경비원, 분류, 판단 코드를 돌립니다. 그 시점까지의 기록만 쓰므로, 노즐 막힘은 청소한 뒤
        온도 센서로 바뀔 수 있습니다. 장비 시각 {watch.sim_time ? time(watch.sim_time) : "-"}
        {watch.sim_speed ? ` · 속도 ×${watch.sim_speed}` : ""}
      </p>
      {watch.status === "error" && <p className="hint analysis-error">감시 오류: {watch.error}</p>}
      {error && <p className="hint analysis-error">{error}</p>}
      {alerts.length === 0 ? (
        <p className="hint">이번 런에서 아직 경보가 없습니다.</p>
      ) : (
        <div className="table-wrap">
          <table className="alarm-table">
            <thead>
              <tr>
                <th>경보 시각</th>
                <th>원인 (코드 판단)</th>
                <th>근거</th>
                <th>조치 (안내서)</th>
                <th>설비 알람</th>
                <th>반장 보고서</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => {
                const report = reports[`${watch.run_id}/${a.started_at}`];
                return (
                <Fragment key={a.started_at}>
                <tr>
                  <td className="mono">{time(a.started_at)}</td>
                  <td>
                    {a.cause_label}
                    <div className="muted small">{a.basis}</div>
                    {a.recheck_after_clean && <div className="muted small">청소 후 폭으로 다시 판단</div>}
                  </td>
                  <td className="detail">{evidenceLine(a)}</td>
                  <td className="detail">{a.actions?.steps ?? "-"}</td>
                  <td>
                    {a.first_alarm ? (
                      <>
                        <span className="mono">
                          {a.first_alarm.code} {time(a.first_alarm.at)}
                        </span>
                        <div className="small">{leadText(a)}</div>
                      </>
                    ) : (
                      <span className="muted small">아직 없음</span>
                    )}
                  </td>
                  <td>
                    <button className="btn-text live-report-btn" disabled={writing !== null} onClick={() => write(a.started_at)}>
                      {writing === a.started_at ? "작성 중…" : report ? "다시 쓰기" : "보고서 쓰기"}
                    </button>
                  </td>
                </tr>
                {report && (
                  <tr>
                    <td colSpan={6}>
                      <Report report={report} />
                    </td>
                  </tr>
                )}
                </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
