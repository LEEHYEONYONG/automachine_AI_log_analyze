import { useEffect, useState } from "react";
import { FAULT_LABEL } from "../labels";

// The analysis API runs in its own container; Vite proxies /api/analysis to it.
const API = "/api/analysis";
// Repeats of the same fault within this many minutes are shown as one row (same as eval/README.md).
const GROUP_MIN = 60;

const time = (t) => t.slice(11, 19);
const num = (v, digits = 1) => Number(v).toFixed(digits);

/** One line of evidence per rule, from the evidence dict each rule leaves in rules.py. */
function evidenceText(type, e) {
  if (type === "air_supply_drop") {
    return `압력 ${num(e.pressure_kpa)} kPa, 진공 ${num(e.vacuum_kpa)} kPa 상태가 토출 중 ${e.consecutive}번 연속`;
  }
  if (type === "vacuum_leak") {
    return `진공 중앙값 ${num(e.vacuum_median_kpa)} kPa로 약해짐 (압력 중앙값 ${num(e.pressure_median_kpa)} kPa는 정상)`;
  }
  if (type === "nozzle_clog") {
    return `비드 폭 중앙값 ${num(e.width_median_30min_ago_mm, 3)} → ${num(e.width_median_mm, 3)} mm (30분 사이), ${e.recipe}`;
  }
  return Object.entries(e).map(([k, v]) => `${k}=${v}`).join(", ");
}

function groupRepeats(candidates) {
  const rows = [];
  const last = {};
  for (const c of candidates) {
    const at = new Date(c.detected_at).getTime();
    const g = last[c.fault_type];
    if (g && at - g.start <= GROUP_MIN * 60_000) {
      g.repeats += 1;
      continue;
    }
    last[c.fault_type] = { ...c, start: at, repeats: 1 };
    rows.push(last[c.fault_type]);
  }
  return rows;
}

export function AnalysisPage() {
  const [runs, setRuns] = useState([]);
  const [runId, setRunId] = useState("");
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
      const res = await fetch(`${API}/runs/${runId}`, { method: "POST" });
      if (!res.ok) throw new Error(`분석 실패 (${res.status})`);
      setResult(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const rows = result ? groupRepeats(result.candidates) : [];

  return (
    <main className="console">
      <section className="panel">
        <h2>AI 분석 (1주차: 규칙 기반)</h2>
        <p className="hint">DB에 적재된 실행을 골라 분석하면, 규칙이 찾은 고장 후보와 근거가 나옵니다.</p>
        <div className="form-row">
          <select value={runId} onChange={(e) => setRunId(e.target.value)}>
            {runs.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.run_id}
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
            고장 후보 · <span className="mono">{result.run_id}</span>
          </h2>
          {rows.length === 0 ? (
            <p className="hint">규칙이 찾은 고장 후보가 없습니다.</p>
          ) : (
            <div className="table-wrap">
              <table className="alarm-table">
                <thead>
                  <tr>
                    <th>탐지 시각</th>
                    <th>고장 종류</th>
                    <th>근거</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={`${r.fault_type}-${r.detected_at}`}>
                      <td className="mono">{time(r.detected_at)}</td>
                      <td>
                        {FAULT_LABEL[r.fault_type] ?? r.fault_type}
                        {r.repeats > 1 && <span className="muted small"> · 반복 {r.repeats}번</span>}
                      </td>
                      <td className="detail">{evidenceText(r.fault_type, r.evidence)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
