import { tr } from "../prefs";
import { useEffect, useState } from "react";
import { anomalyText, evidenceText, FEATURE, faultName, time } from "./evidence";
import { HandoverPanel } from "./Handover";
import { IncidentChart } from "./IncidentChart";
import { LivePanel } from "./LiveWatch";
import { Glossary, IncidentSummary } from "./PlainSummary";
import { runName, TERM, TERM_HELP } from "./plain";
import { Report } from "./Report";

// The analysis API runs in its own container; Vite proxies /api/analysis to it.
const API = "/api/analysis";
// Repeats of the same fault within this many minutes are shown as one row (same as eval/README.md).
const GROUP_MIN = 60;

const METHODS = ["rule", "anomaly", "classify"];

function groupRepeats(candidates) {
  const rows = [];
  const last = {};
  for (const c of candidates) {
    const at = new Date(c.detected_at).getTime();
    // Every guard result has fault_type "anomaly", so it groups by which value went off instead.
    const key = c.fault_type === "anomaly" ? c.evidence.feature : c.fault_type;
    const g = last[key];
    if (g && at - g.start <= GROUP_MIN * 60_000) {
      g.repeats += 1;
      continue;
    }
    last[key] = { ...c, key, start: at, repeats: 1 };
    rows.push(last[key]);
  }
  return rows;
}

/** Incidents for one run. Reports are written one at a time because the model takes up to a few minutes on one GPU. */
function ForemanPanel({ runId }) {
  const [incidents, setIncidents] = useState(null);
  const [writing, setWriting] = useState(null);
  const [error, setError] = useState(null);
  // Which incidents have their pressure/vacuum graph open. Closed by default so the list stays short.
  const [charts, setCharts] = useState({});

  useEffect(() => {
    let current = true;
    fetch(`${API}/runs/${runId}/incidents`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(tr("사건을 불러오지 못했습니다 ({a})", { a: res.status })))))
      .then((data) => current && setIncidents(data.incidents))
      .catch((e) => current && setError(e.message));
    return () => {
      current = false;
    };
  }, [runId]);

  const write = async (at) => {
    setWriting(at);
    setError(null);
    try {
      const res = await fetch(`${API}/runs/${runId}/incidents/report?at=${encodeURIComponent(at)}`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? tr("보고서를 쓰지 못했습니다 ({a})", { a: res.status }));
      }
      const report = await res.json();
      setIncidents((list) => list.map((i) => (i.started_at === at ? { ...i, report } : i)));
    } catch (e) {
      setError(e.message);
    } finally {
      setWriting(null);
    }
  };

  return (
    <section className="panel">
      <h2>{tr("이상 건과 원인 판정")}</h2>
      <p className="hint">
        {tr("가까운 시각에 울린 경보를 이상 건 하나로 묶고, 코드가 정해진 순서로 원인을 판정합니다. \"보고서 쓰기\"를 누르면 AI(LLM)가 기록을 찾아보고 판정의 근거를 글로 씁니다. AI는 원인을 바꾸지 못하고, 할 일은 조치 매뉴얼에서 가져옵니다. 보고서는 한 건에 1분 안팎 걸립니다.")}
      </p>
      {error && <p className="hint analysis-error">{error}</p>}
      {incidents === null && !error && <p className="hint">{tr("이상 건을 찾는 중…")}</p>}
      {incidents?.length === 0 && <p className="hint">{tr("이 런에는 경보가 없습니다.")}</p>}
      {incidents?.map((i) => (
        <div className="incident" key={i.started_at}>
          <div className="incident-head">
            <div>
              <span className="mono">
                {time(i.started_at)} ~ {time(i.last_at)}
              </span>{" "}
              <strong>{faultName(i.cause)}</strong>
            </div>
            <div className="incident-buttons">
              <button className="btn btn-secondary" aria-expanded={!!charts[i.started_at]} onClick={() => setCharts((c) => ({ ...c, [i.started_at]: !c[i.started_at] }))}>
                {charts[i.started_at] ? tr("그래프 닫기") : tr("압력·진공 그래프")}
              </button>
              <button className="btn" disabled={writing !== null} onClick={() => write(i.started_at)}>
                {writing === i.started_at ? tr("작성 중…") : i.report ? tr("다시 쓰기") : tr("보고서 쓰기")}
              </button>
            </div>
          </div>
          <IncidentSummary incident={i} />
          {charts[i.started_at] && <IncidentChart runId={runId} at={i.started_at} until={i.last_at} />}
          {i.report && <Report report={i.report} />}
        </div>
      ))}
    </section>
  );
}

export function AnalysisPage() {
  const [runs, setRuns] = useState([]);
  const [runId, setRunId] = useState("");
  const [method, setMethod] = useState("rule");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API}/runs`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(tr("분석 서버 응답 {a}", { a: res.status })))))
      .then((list) => {
        setRuns(list);
        setRunId((id) => id || list.at(-1)?.run_id || "");
      })
      .catch((e) => setError(e.message));
  }, []);

  const analyze = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/runs/${runId}?method=${method}`, { method: "POST" });
      if (!res.ok) throw new Error(tr("분석 실패 ({a})", { a: res.status }));
      setResult(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const rows = result ? groupRepeats(result.candidates) : [];
  const isAnomaly = result?.method === "anomaly";
  const isClassify = result?.method === "classify";

  return (
    <main className="console">
      <Glossary />
      <LivePanel />
      <section className="panel">
        <h2>{tr("지난 런 분석")}</h2>
        <p className="hint">{TERM_HELP[method]}</p>
        <div className="form-row">
          <select value={runId} onChange={(e) => setRunId(e.target.value)} aria-label={tr("런")} title={tr("런")}>
            {runs.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {runName(r.run_id)}
              </option>
            ))}
          </select>
          <select value={method} onChange={(e) => setMethod(e.target.value)} aria-label={tr("분석 방법")}>
            {METHODS.map((value) => (
              <option key={value} value={value}>
                {TERM[value]}
              </option>
            ))}
          </select>
          <button className="btn" disabled={!runId || busy} onClick={analyze}>
            {busy ? tr("분석 중…") : tr("분석")}
          </button>
        </div>
        {error && <p className="hint analysis-error">{error}</p>}
      </section>

      {result && (
        <section className="panel">
          <h2>
            {tr("{a} 결과", { a: TERM[result.method] })} · {runName(result.run_id)}
          </h2>
          {rows.length === 0 ? (
            <p className="hint">
              {isAnomaly || isClassify ? tr("정상 범위를 벗어난 값이 없습니다.") : tr("알려진 고장 패턴과 일치하는 기록이 없습니다.")}
            </p>
          ) : (
            <div className="table-wrap">
              <table className="alarm-table">
                <thead>
                  <tr>
                    <th>{tr("탐지 시각")}</th>
                    <th>{isAnomaly ? tr("정상 범위를 벗어난 값") : tr("고장 종류")}</th>
                    <th>{tr("근거")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={`${r.key}-${r.detected_at}`}>
                      <td className="mono">{time(r.detected_at)}</td>
                      <td>
                        {isAnomaly ? FEATURE[r.evidence.feature].label : faultName(r.fault_type)}
                        {r.repeats > 1 && <span className="muted small"> {tr("· 반복 {a}번", { a: r.repeats })}</span>}
                      </td>
                      <td className="detail">
                        {isClassify &&
                          tr("{a} 이상 → 지난 {b} 사례와 {c}% 비슷 · ", { a: FEATURE[r.evidence.feature].label, b: faultName(r.evidence.best_guess), c: Math.round(r.confidence * 100) })}
                        {isAnomaly || isClassify ? anomalyText(r.evidence) : evidenceText(r.fault_type, r.evidence)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {result && <ForemanPanel key={result.run_id} runId={result.run_id} />}
      {result && <HandoverPanel key={`handover-${result.run_id}`} runId={result.run_id} />}
    </main>
  );
}
