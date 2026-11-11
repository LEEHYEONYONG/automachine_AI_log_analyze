import { tr } from "../prefs";
import { Fragment, useState } from "react";
import { ACTION_LABEL } from "../labels";
import { evidenceText, time } from "./evidence";
import { plainBasis, plainText, runName, TERM } from "./plain";
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
  if (!loaded.ok) await fail(loaded, tr("지금 런을 불러오지 못했습니다"));
  const res = await fetch(`${API}/runs/${runId}/incidents/report?at=${encodeURIComponent(at)}`, { method: "POST" });
  if (!res.ok) await fail(res, tr("보고서를 쓰지 못했습니다"));
  return res.json();
}

function leadText(alert) {
  if (!alert.first_alarm) return tr("관련 설비 알람 아직 없음");
  const lead = alert.lead_min;
  return lead >= 0
    ? tr("설비 알람 {a}보다 {b}분 먼저", { a: alert.first_alarm.code, b: Math.round(lead) })
    : tr("설비 알람 {a}보다 {b}분 늦게", { a: alert.first_alarm.code, b: Math.round(-lead) });
}

function evidenceLine(alert) {
  return alert.evidence ? plainText(evidenceText(alert.evidence.type, alert.evidence.data)) : plainBasis(alert.basis);
}

/** What the operator did after the alert, and whether the watch counts it as fixed. */
function fixLine(alert) {
  if (!alert.fixed_by) return null;
  const { action, at } = alert.fixed_by;
  const what = action === "recipe_change" ? tr("레시피 수정") : (ACTION_LABEL[action] ?? action);
  return alert.settled
    ? tr("{a} {b} 조치 뒤 정상", { a: what, b: time(at) })
    : tr("{a} {b} 조치함 · 정상인지 확인 중", { a: what, b: time(at) });
}

/** A strip under the header on every tab. Shows the newest AI alert until it is dismissed, settled, or a newer one arrives. */
export function LiveAlertBar({ onOpen }) {
  const watch = useWatch();
  const [hidden, setHidden] = useState(null);
  const alerts = watch?.alerts ?? [];
  const newest = alerts.at(-1);
  if (!newest || newest.settled || hidden === `${watch.run_id}/${newest.started_at}`) return null;
  return (
    <div className="live-bar" role="status">
      <button className="live-bar-main" onClick={onOpen} title={tr("AI 분석 탭에서 경보 목록 보기")}>
        <span className="live-bar-tag">{tr("AI 예측 경보")}</span>
        <span className="mono">{time(newest.started_at)}</span>
        <strong>{newest.cause_label}</strong>
        <span className="live-bar-evidence">{evidenceLine(newest)}</span>
        <span className="live-bar-lead">{leadText(newest)}</span>
        {alerts.length > 1 && <span className="muted small">{tr("외 {a}건", { a: alerts.length - 1 })}</span>}
      </button>
      <button className="btn-text" aria-label={tr("경보 숨기기")} onClick={() => setHidden(`${watch.run_id}/${newest.started_at}`)}>
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
        <h2>{tr("실시간 감시")}</h2>
        <p className="hint">{tr("실시간 감시에 연결하지 못했습니다. k8s에서만 동작합니다.")}</p>
      </section>
    );
  }
  const alerts = [...watch.alerts].reverse();
  return (
    <section className="panel">
      <h2>
        {tr("실시간 감시")} · {watch.run_id ? runName(watch.run_id) : "-"}
      </h2>
      <p className="hint">
        {tr("지금 가동 중인 장비의 기록을 1초마다 이어 읽어 {a}·{b}·{c}·{d}를 합니다. 그 시점까지의 기록만 쓰므로, 노즐 막힘은 노즐을 청소한 뒤에야 온도 센서 문제로 바뀔 수 있습니다.", { a: TERM.rule, b: TERM.anomaly, c: TERM.classify, d: TERM.decide })}{" "}
        {tr("장비 시각 {a}", { a: watch.sim_time ? time(watch.sim_time) : "-" })}
        {watch.sim_speed ? tr(" · 속도 ×{a}", { a: watch.sim_speed }) : ""}
      </p>
      {watch.status === "error" && <p className="hint analysis-error">{tr("감시 오류: {a}", { a: watch.error })}</p>}
      {error && <p className="hint analysis-error">{error}</p>}
      {alerts.length === 0 ? (
        <p className="hint">{tr("이번 런에서 아직 경보가 없습니다.")}</p>
      ) : (
        <div className="table-wrap">
          <table className="alarm-table">
            <thead>
              <tr>
                <th>{tr("경보 시각")}</th>
                <th>{TERM.decide}</th>
                <th>{tr("근거")}</th>
                <th>{tr("할 일 (조치 매뉴얼)")}</th>
                <th>{tr("설비 알람")}</th>
                <th>{TERM.report}</th>
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
                    <div className="muted small">{plainBasis(a.basis)}</div>
                    {a.recheck_after_clean && <div className="muted small">{tr("노즐 청소 뒤 비드 폭을 보고 다시 판정합니다")}</div>}
                    {a.fixed_by && <div className="small">{a.settled ? "✔ " : ""}{fixLine(a)}</div>}
                  </td>
                  <td className="detail">{evidenceLine(a)}</td>
                  <td className="detail">{a.actions?.steps ? plainText(a.actions.steps) : "-"}</td>
                  <td>
                    {a.first_alarm ? (
                      <>
                        <span className="mono">
                          {a.first_alarm.code} {time(a.first_alarm.at)}
                        </span>
                        <div className="small">{leadText(a)}</div>
                      </>
                    ) : (
                      <span className="muted small">{tr("아직 없음")}</span>
                    )}
                  </td>
                  <td>
                    <button className="btn-text live-report-btn" disabled={writing !== null} onClick={() => write(a.started_at)}>
                      {writing === a.started_at ? tr("작성 중…") : report ? tr("다시 쓰기") : tr("보고서 쓰기")}
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
