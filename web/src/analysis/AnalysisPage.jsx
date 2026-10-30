import { useEffect, useState } from "react";
import { FAULT_LABEL } from "../labels";

// The analysis API runs in its own container; Vite proxies /api/analysis to it.
const API = "/api/analysis";
// Repeats of the same fault within this many minutes are shown as one row (same as eval/README.md).
const GROUP_MIN = 60;

const METHOD_LABEL = { rule: "규칙", anomaly: "경비원" };
const METHOD_HINT = {
  rule: "규칙은 고장 이름까지 알려 주지만, 규칙을 만들어 둔 고장만 찾습니다.",
  anomaly: "경비원은 정상 구간에서 배운 평소 모습과 다른 값을 알려 줍니다. 처음 보는 고장도 찾지만, 고장 이름은 모릅니다.",
};
// The values the guard watches (FEATURES in analysis/app/anomaly.py).
const FEATURE = {
  bead_width_mm: { label: "비드 폭", unit: "mm", digits: 3 },
  bead_offset_mm: { label: "비드 오프셋", unit: "mm", digits: 3 },
  disp_pressure_kpa: { label: "토출 압력", unit: "kPa", digits: 1 },
  vacuum_kpa: { label: "진공", unit: "kPa", digits: 1 },
  ng_10min: { label: "10분 불량 수" },
};

const time = (t) => t.slice(11, 19);
const num = (v, digits = 1) => Number(v).toFixed(digits);

/** One line of evidence for the guard, from the evidence dict in anomaly.py. */
function anomalyText(e) {
  if (e.feature === "ng_10min") {
    return `최근 10분 불량 ${e.count_10min}개 (평소 최대 ${e.normal_max}개), ${e.recipe}`;
  }
  const { unit, digits } = FEATURE[e.feature];
  const usual = `${num(e.normal_mean, digits)} ± ${num(e.normal_std, digits)} ${unit}`;
  return `${num(e.value, digits)} ${unit} (평소 ${usual}, 표준편차의 ${num(Math.abs(e.z))}배 벗어남), ${e.recipe}`;
}

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
  if (type === "recipe_pressure_error" || type === "recipe_retract_error") {
    return `${e.by}가 ${e.param}를 ${e.old} → ${e.new}로 변경 (표준 ${e.standard}, ${e.deviation_pct}%), ${e.recipe}`;
  }
  if (type === "air_bubble") {
    return `BEAD_VOID 불량이 ${e.window_min}분 안에 ${e.void_count}개 (첫 VOID ${time(e.first_void_at)}), ${e.recipe}`;
  }
  if (type === "needle_offset") {
    return `최근 ${e.window}개 제품의 비드 오프셋 중앙값 ${num(e.offset_median_mm, 3)} mm (정상 약 0.010, 불량 기준 0.10), ${e.recipe}`;
  }
  if (type === "needle_tip_buildup") {
    return `STRINGING 불량이 ${e.window_min}분 안에 ${e.stringing_count}개 (첫 STRINGING ${time(e.first_stringing_at)}, retract 설정은 정상), ${e.recipe}`;
  }
  return Object.entries(e).map(([k, v]) => `${k}=${v}`).join(", ");
}

function groupRepeats(candidates) {
  const rows = [];
  const last = {};
  for (const c of candidates) {
    const at = new Date(c.detected_at).getTime();
    // Every guard result has fault_type "anomaly", so it groups by which value went off instead.
    const key = c.evidence.feature ?? c.fault_type;
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

  return (
    <main className="console">
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
              {isAnomaly ? "경비원이 평소와 다른 값을 찾지 못했습니다." : "규칙이 찾은 고장 후보가 없습니다."}
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
                        {isAnomaly ? FEATURE[r.evidence.feature].label : (FAULT_LABEL[r.fault_type] ?? r.fault_type)}
                        {r.repeats > 1 && <span className="muted small"> · 반복 {r.repeats}번</span>}
                      </td>
                      <td className="detail">
                        {isAnomaly ? anomalyText(r.evidence) : evidenceText(r.fault_type, r.evidence)}
                      </td>
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
