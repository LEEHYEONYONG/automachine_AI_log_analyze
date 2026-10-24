import { useState } from "react";
import { useMeta } from "../../api";
import { STATION_LABEL, STATION_STATE_LABEL } from "../../labels";

import { CONDITION_LABEL, STEP_LABEL, WAIT_LABEL, standardTime } from "../hmiLabels";

const SLOW = 1.2; // a step taking 20% longer than standard is flagged

function initialStation() {
  return location.hash.split("/")[2] || "DISPENSER";
}

/** Per-station step sequence: the standard steps, where the station is now, and how long recent steps took. */
export function SequencePage({ state }) {
  const meta = useMeta();
  const [name, setName] = useState(initialStation);
  const station = state.stations.find((s) => s.name === name) ?? state.stations[0];
  const sequence = meta?.sequences[station.name] ?? [];
  const stdOf = (step) => {
    const def = sequence.find((d) => d.step === step);
    return def ? standardTime(step, def.std_s, state.setpoints) : null;
  };

  return (
    <div className="page">
      <div className="station-tabs" role="tablist">
        {state.stations.map((s) => (
          <button
            key={s.name}
            role="tab"
            aria-selected={s.name === station.name}
            className={`station-tab st-${s.state} ${s.name === station.name ? "active" : ""}`}
            onClick={() => setName(s.name)}
          >
            <strong>{STATION_LABEL[s.name] ?? s.name}</strong>
            <span>{s.step ? STEP_LABEL[s.step] ?? s.step : WAIT_LABEL[s.wait] ?? STATION_STATE_LABEL[s.state]}</span>
          </button>
        ))}
      </div>

      <div className="sequence-grid">
        <section className="panel">
          <h2>{STATION_LABEL[station.name]} 표준 시퀀스</h2>
          <div className="table-wrap">
            <table className="seq-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>스텝</th>
                  <th>동작</th>
                  <th>기준 시간</th>
                  <th>조건</th>
                  <th>진행</th>
                </tr>
              </thead>
              <tbody>
                {sequence.map((d, i) => {
                  const current = d.step === station.step;
                  const std = standardTime(d.step, d.std_s, state.setpoints);
                  return (
                    <tr key={d.step} className={current ? "current" : d.condition ? "conditional" : ""}>
                      <td className="mono">{String(i + 1).padStart(2, "0")}</td>
                      <td className="mono">{d.step}</td>
                      <td>{STEP_LABEL[d.step] ?? d.step}</td>
                      <td className="mono">{std !== null ? `${std.toFixed(2)}s` : "-"}</td>
                      <td>{CONDITION_LABEL[d.condition] ?? d.condition}</td>
                      <td className="seq-progress">
                        {current && (
                          <div className="step-bar">
                            <div className="step-bar-fill" style={{ width: `${station.progress * 100}%` }} />
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <div className="col">
          <StationStatus station={station} />
          <section className="panel">
            <h2>최근 스텝 실적</h2>
            {station.history.length === 0 ? (
              <p className="hint">아직 완료된 스텝이 없습니다.</p>
            ) : (
              <table className="seq-table">
                <thead>
                  <tr>
                    <th>완료</th>
                    <th>스텝</th>
                    <th>실적</th>
                    <th>기준</th>
                  </tr>
                </thead>
                <tbody>
                  {station.history.map((h, i) => {
                    const std = stdOf(h.step);
                    const slow = std !== null && std > 0 && h.t > std * SLOW;
                    return (
                      <tr key={`${h.end}-${i}`} className={slow ? "slow" : ""}>
                        <td className="mono">{h.end.slice(11, 21)}</td>
                        <td>{STEP_LABEL[h.step] ?? h.step}</td>
                        <td className="mono">{h.t.toFixed(3)}s</td>
                        <td className="mono">{std !== null ? `${std.toFixed(2)}s` : "-"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
            <p className="hint">기준보다 20% 이상 느린 스텝은 강조됩니다. 실린더 스텝이 느려지면 에어 압력을 의심해 보세요.</p>
          </section>
        </div>
      </div>
    </div>
  );
}

function StationStatus({ station }) {
  return (
    <section className="panel">
      <h2>스테이션 상태</h2>
      <dl className="kv">
        <dt>상태</dt>
        <dd className={`st-text-${station.state}`}>{STATION_STATE_LABEL[station.state]}</dd>
        <dt>현재 스텝</dt>
        <dd>{station.step ? `${STEP_LABEL[station.step] ?? station.step} (${station.step})` : "-"}</dd>
        <dt>대기 사유</dt>
        <dd>{WAIT_LABEL[station.wait] ?? "-"}</dd>
        <dt>제품</dt>
        <dd className="mono">{station.wp ?? "-"}</dd>
        <dt>판정</dt>
        <dd>{station.judge || "-"}</dd>
      </dl>
    </section>
  );
}
