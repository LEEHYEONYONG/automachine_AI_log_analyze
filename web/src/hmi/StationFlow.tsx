import { STATION_LABEL, STATION_STATE_LABEL } from "../labels";
import type { StationView } from "../types";

export function StationFlow({ stations }: { stations: StationView[] }) {
  return (
    <section className="panel">
      <h2>공정 흐름</h2>
      <div className="flow">
        {stations.map((s, i) => (
          <div className="flow-item" key={s.name}>
            <div className={`station st-${s.state}`}>
              <div className="station-head">
                <span className="station-name">{STATION_LABEL[s.name] ?? s.name}</span>
                <span className="station-code">{s.name}</span>
              </div>
              <div className="station-state">{STATION_STATE_LABEL[s.state]}</div>
              <dl className="station-detail">
                <dt>스텝</dt>
                <dd className="mono">{s.step || "-"}</dd>
                <dt>제품</dt>
                <dd className="mono">{s.wp ? s.wp.slice(-9) : "-"}</dd>
              </dl>
            </div>
            {i < stations.length - 1 && <div className="flow-arrow" aria-hidden>▶</div>}
          </div>
        ))}
      </div>
    </section>
  );
}
