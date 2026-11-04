import { useEffect, useState } from "react";
import { anomalyText, evidenceText, FEATURE, faultName, time } from "./evidence";
import { HandoverPanel } from "./Handover";
import { LivePanel } from "./LiveWatch";
import { Report } from "./Report";

// The analysis API runs in its own container; Vite proxies /api/analysis to it.
const API = "/api/analysis";
// Repeats of the same fault within this many minutes are shown as one row (same as eval/README.md).
const GROUP_MIN = 60;

const METHOD_LABEL = { rule: "규칙", anomaly: "경비원", classify: "분류" };
const METHOD_HINT = {
  rule: "규칙은 고장 이름까지 알려 주지만, 규칙을 만들어 둔 고장만 찾습니다.",
  anomaly: "경비원은 정상 구간에서 배운 평소 모습과 다른 값을 알려 줍니다. 처음 보는 고장도 찾지만, 고장 이름은 모릅니다.",
  classify: "분류는 경비원이 울린 순간의 값을 보고 지금까지의 예시에서 배운 고장 이름을 고릅니다. 규칙보다 자주 틀리므로 참고용입니다.",
};

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

  useEffect(() => {
    let current = true;
    fetch(`${API}/runs/${runId}/incidents`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`사건을 불러오지 못했습니다 (${res.status})`))))
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
        throw new Error(body.detail ?? `보고서를 쓰지 못했습니다 (${res.status})`);
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
      <h2>반장 보고서</h2>
      <p className="hint">
        규칙과 경비원의 경보를 사건으로 묶어 코드가 원인을 정합니다. AI는 기록을 조회해 근거를 설명할 뿐 원인을 바꾸지 못하고, 조치는 안내서에서
        가져옵니다. 보고서는 한 건에 1분 안팎 걸립니다.
      </p>
      {error && <p className="hint analysis-error">{error}</p>}
      {incidents === null && !error && <p className="hint">사건을 찾는 중…</p>}
      {incidents?.length === 0 && <p className="hint">이 런에는 경보가 없습니다.</p>}
      {incidents?.map((i) => (
        <div className="incident" key={i.started_at}>
          <div className="incident-head">
            <div>
              <div>
                <span className="mono">
                  {time(i.started_at)} ~ {time(i.last_at)}
                </span>{" "}
                <strong>{faultName(i.cause)}</strong>
              </div>
              <div className="small">{i.basis}</div>
              <div className="small muted">
                규칙: {i.rule_names.map(faultName).join(", ") || "없음"} · 경비원:{" "}
                {i.guard_values.map((v) => FEATURE[v].label).join(", ") || "없음"} · 분류:{" "}
                {i.tree_guess ? faultName(i.tree_guess) : "없음"}
              </div>
            </div>
            <button className="btn" disabled={writing !== null} onClick={() => write(i.started_at)}>
              {writing === i.started_at ? "작성 중…" : i.report ? "다시 쓰기" : "보고서 쓰기"}
            </button>
          </div>
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
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`분석 서버 응답 ${res.status}`))))
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
      if (!res.ok) throw new Error(`분석 실패 (${res.status})`);
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
      <LivePanel />
      <section className="panel">
        <h2>AI 분석</h2>
        <p className="hint">{METHOD_HINT[method]}</p>
        <div className="form-row">
          <select value={runId} onChange={(e) => setRunId(e.target.value)}>
            {runs.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.run_id}
              </option>
            ))}
          </select>
          <select value={method} onChange={(e) => setMethod(e.target.value)}>
            {Object.entries(METHOD_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <button className="btn" disabled={!runId || busy} onClick={analyze}>
            {busy ? "분석 중…" : "분석"}
          </button>
        </div>
        {error && <p className="hint analysis-error">{error}</p>}
      </section>

      {result && (
        <section className="panel">
          <h2>
            {METHOD_LABEL[result.method]} 결과 · <span className="mono">{result.run_id}</span>
          </h2>
          {rows.length === 0 ? (
            <p className="hint">
              {isAnomaly || isClassify ? "경비원이 평소와 다른 값을 찾지 못했습니다." : "규칙이 찾은 고장 후보가 없습니다."}
            </p>
          ) : (
            <div className="table-wrap">
              <table className="alarm-table">
                <thead>
                  <tr>
                    <th>탐지 시각</th>
                    <th>{isAnomaly ? "평소와 다른 값" : "고장 종류"}</th>
                    <th>근거</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={`${r.key}-${r.detected_at}`}>
                      <td className="mono">{time(r.detected_at)}</td>
                      <td>
                        {isAnomaly ? FEATURE[r.evidence.feature].label : faultName(r.fault_type)}
                        {r.repeats > 1 && <span className="muted small"> · 반복 {r.repeats}번</span>}
                      </td>
                      <td className="detail">
                        {isClassify &&
                          `${FEATURE[r.evidence.feature].label} 경보, ${faultName(r.evidence.best_guess)} 예시와 ${Math.round(r.confidence * 100)}% 일치 · `}
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
