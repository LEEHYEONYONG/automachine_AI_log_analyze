import { ACTION_LABEL, FAULT_LABEL, FAULT_PARAM_LABEL, FAULT_STATE_LABEL } from "../labels";
import type { FaultTruth } from "../types";

const time = (t: string | null) => (t ? t.slice(11, 19) : "-");

export function FaultList({ faults }: { faults: FaultTruth[] }) {
  return (
    <section className="panel">
      <h2>고장 현황 (정답)</h2>
      {faults.length === 0 && <p className="hint">주입된 고장이 없습니다.</p>}
      <div className="fault-list">
        {faults.map((f) => (
          <article key={f.fault_id} className={`fault fault-${f.state_at_end}`}>
            <div className="fault-head">
              <span className="mono">{f.fault_id}</span>
              <strong>{FAULT_LABEL[f.type] ?? f.type}</strong>
              <span className="tag">{f.unit}</span>
              <span className={`fault-state fs-${f.state_at_end}`}>{FAULT_STATE_LABEL[f.state_at_end]}</span>
            </div>

            <dl className="kv small">
              <dt>예약</dt>
              <dd className="mono">{time(f.scheduled_at)}</dd>
              <dt>발생</dt>
              <dd className="mono">{time(f.injected_at)}</dd>
              <dt>해결</dt>
              <dd className="mono">
                {time(f.resolved_at)}
                {f.resolved_by && ` · ${ACTION_LABEL[f.resolved_by] ?? f.resolved_by}`}
              </dd>
              {Object.entries(f.params).map(([k, v]) => (
                <ParamRow key={k} label={FAULT_PARAM_LABEL[k] ?? k} value={v} />
              ))}
            </dl>

            {f.state_at_end === "active" && (
              <div className="progress" title="고장 진행률">
                <div className="progress-fill" style={{ width: `${f.progress * 100}%` }} />
                <span>{Math.round(f.progress * 100)}%</span>
              </div>
            )}

            <details>
              <summary>예상 증상</summary>
              <ul>
                {f.expected_symptoms.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </details>
          </article>
        ))}
      </div>
    </section>
  );
}

function ParamRow({ label, value }: { label: string; value: number }) {
  return (
    <>
      <dt>{label}</dt>
      <dd className="mono">{value}</dd>
    </>
  );
}
