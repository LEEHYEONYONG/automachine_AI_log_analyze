import { STATION_LABEL, STATION_STATE_LABEL } from "../labels";

import { STEP_LABEL, WAIT_LABEL } from "./hmiLabels";

export function StationFlow({ stations, onSelect }) {
  return (
    <section className="panel">
      <h2>공정 흐름</h2>
      <div className="flow">
        <div className="flow-edge">이전 공정</div>
        {stations.map((s) => (
          <div className="flow-item" key={s.name}>
            <div className="flow-arrow" aria-hidden>▶</div>
            <button className={`station st-${s.state}`} onClick={() => onSelect?.(s.name)} title="시퀀스 보기">
              <div className="station-head">
                <span className="station-name">{STATION_LABEL[s.name] ?? s.name}</span>
                <span className="station-code">{s.name}</span>
              </div>
              <div className="station-state">{STATION_STATE_LABEL[s.state]}</div>
              <div className="station-step">{s.step ? STEP_LABEL[s.step] ?? s.step : WAIT_LABEL[s.wait] ?? "-"}</div>
              <div className="step-bar" aria-hidden>
                <div className="step-bar-fill" style={{ width: `${s.step ? s.progress * 100 : 0}%` }} />
              </div>
              <div className="station-wp mono">{s.wp ? s.wp.slice(-9) : "제품 없음"}</div>
            </button>
          </div>
        ))}
        <div className="flow-arrow" aria-hidden>▶</div>
        <div className="flow-edge">다음 공정</div>
      </div>
    </section>
  );
}
