import { tr } from "../prefs";
import { ACTION_LABEL, FAULT_LABEL, FAULT_PARAM_LABEL, FAULT_STATE_LABEL, OPERATOR_ONLY_ACTION_LABEL } from "../labels";

const time = (t) => (t ? t.slice(11, 19) : "-");
const actionLabel = (a) => ACTION_LABEL[a] ?? OPERATOR_ONLY_ACTION_LABEL[a] ?? a;

function originLabel(origin) {
  if (origin === "injected") return { tag: tr("주입"), text: "" };
  const [kind, ...rest] = origin.split(": ");
  return { tag: kind === "operator_error" ? tr("작업자 실수") : tr("자연 발생"), text: rest.join(": ") };
}

export function FaultList({ faults }) {
  return (
    <section className="panel">
      <h2>{tr("고장 현황 (정답)")}</h2>
      {faults.length === 0 && <p className="hint">{tr("주입된 고장이 없습니다.")}</p>}
      <div className="fault-list">
        {faults.map((f) => (
          <article key={f.fault_id} className={`fault fault-${f.state_at_end}`}>
            <div className="fault-head">
              <span className="mono">{f.fault_id}</span>
              <strong>{FAULT_LABEL[f.type] ?? f.type}</strong>
              <span className="tag">{f.unit}</span>
              <span className={`tag origin-${f.origin.split(":")[0]}`}>{originLabel(f.origin).tag}</span>
              <span className={`fault-state fs-${f.state_at_end}`}>{FAULT_STATE_LABEL[f.state_at_end]}</span>
            </div>
            {originLabel(f.origin).text && <p className="hint">{originLabel(f.origin).text}</p>}

            <dl className="kv small">
              <dt>{tr("예약")}</dt>
              <dd className="mono">{time(f.scheduled_at)}</dd>
              <dt>{tr("발생")}</dt>
              <dd className="mono">{time(f.injected_at)}</dd>
              <dt>{tr("해결")}</dt>
              <dd className="mono">
                {time(f.resolved_at)}
                {f.resolved_by && ` · ${actionLabel(f.resolved_by)}`}
              </dd>
              {Object.entries(f.params).map(([k, v]) => (
                <ParamRow key={k} label={FAULT_PARAM_LABEL[k] ?? k} value={v} />
              ))}
            </dl>

            {f.state_at_end === "active" && (
              <div className="progress" title={tr("고장 진행률")}>
                <div className="progress-fill" style={{ width: `${f.progress * 100}%` }} />
                <span>{Math.round(f.progress * 100)}%</span>
              </div>
            )}

            <details>
              <summary>{tr("예상 증상")}</summary>
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

function ParamRow({ label, value }) {
  return (
    <>
      <dt>{label}</dt>
      <dd className="mono">{value}</dd>
    </>
  );
}
