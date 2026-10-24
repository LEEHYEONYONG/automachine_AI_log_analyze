import { useState } from "react";
import { api } from "../api";
import { ACTION_LABEL, FAULT_LABEL, FAULT_PARAM_LABEL, OPERATOR_ONLY_ACTION_LABEL } from "../labels";

function asStrings(values) {
  return Object.fromEntries(Object.entries(values).map(([k, v]) => [k, String(v)]));
}

export function FaultInjectPanel({ faultTypes, run }) {
  const names = Object.keys(faultTypes);
  const [type, setType] = useState(names[0]);
  const [params, setParams] = useState(() => asStrings(faultTypes[names[0]].defaults));
  const [delay, setDelay] = useState("0");

  const info = faultTypes[type];
  const parsed = Object.fromEntries(Object.entries(params).map(([k, v]) => [k, Number(v)]));
  const valid = Object.values(parsed).every(Number.isFinite) && Number.isFinite(Number(delay)) && Number(delay) >= 0;

  const selectType = (name) => {
    setType(name);
    setParams(asStrings(faultTypes[name].defaults));
  };

  return (
    <section className="panel">
      <h2>고장 주입</h2>
      <div className="form-row">
        <select value={type} onChange={(e) => selectType(e.target.value)}>
          {names.map((n) => (
            <option key={n} value={n}>
              {FAULT_LABEL[n] ?? n}
            </option>
          ))}
        </select>
        <span className="tag">{info.unit}</span>
      </div>
      <p className="hint">{info.description}</p>
      <p className="hint">
        해결 조치:{" "}
        {info.resolved_by.length
          ? info.resolved_by.map((a) => ACTION_LABEL[a] ?? OPERATOR_ONLY_ACTION_LABEL[a] ?? a).join(", ")
          : "없음 (시간이 지나면 저절로 회복)"}
      </p>

      <div className="fields">
        {Object.entries(params).map(([key, value]) => (
          <label key={key} className="field">
            <span>{FAULT_PARAM_LABEL[key] ?? key}</span>
            <input
              type="number"
              step="any"
              value={value}
              onChange={(e) => setParams({ ...params, [key]: e.target.value })}
            />
          </label>
        ))}
        <label className="field">
          <span>시작 지연 (분, 시뮬레이션 시간)</span>
          <input type="number" min={0} step="any" value={delay} onChange={(e) => setDelay(e.target.value)} />
        </label>
      </div>

      <button
        className="btn btn-danger"
        disabled={!valid}
        onClick={() => run(() => api.injectFault(type, parsed, Number(delay)))}
      >
        {Number(delay) > 0 ? `${delay}분 뒤 주입` : "지금 주입"}
      </button>
    </section>
  );
}
