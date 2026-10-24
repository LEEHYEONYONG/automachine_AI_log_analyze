import { api } from "../../api";
import { STATION_LABEL } from "../../labels";

import { AXIS_LABEL, DEVICE_LABEL, PRESET_LABEL } from "../hmiLabels";

const UNITS = ["INFEED", "VISION", "DISPENSER", "INSPECTION", "OUTFEED"];
const JOGS = [-10, -1, -0.1, 0.1, 1, 10];
const VACUUM_OK_KPA = -60;

/** Jog axes and fire cylinders one at a time. Only usable in MANUAL; interlocks are enforced by the machine. */
export function ManualPage({ state, run }) {
  const manual = state.manual;
  const allowed = state.hmi.permissions.manual;
  if (state.op_mode !== "MANUAL" || !manual || !allowed) {
    return (
      <div className="page">
        <section className="panel">
          <h2>수동 조작</h2>
          <p className="hint">
            {allowed
              ? "수동 조작은 MANUAL 모드에서만 할 수 있습니다. 장비를 정지한 뒤 하단의 모드 스위치를 MANUAL로 바꾸세요."
              : "수동 조작은 엔지니어 이상 권한이 필요합니다. 오른쪽 위에서 로그인하세요."}
          </p>
          <button
            className="btn"
            disabled={state.mode === "RUNNING" || !allowed || state.op_mode === "MANUAL"}
            onClick={() => run(() => api.setOpMode("MANUAL"))}
          >
            MANUAL로 전환
          </button>
        </section>
      </div>
    );
  }

  const notReady = [
    ...manual.devices.filter((d) => d.position !== (d.id.endsWith("_STOPPER") ? 1 : 0) || d.position !== d.target),
    ...manual.axes.filter((a) => a.position !== a.home || a.moving),
  ];

  return (
    <div className="page">
      <section className="panel manual-head">
        <div>
          <h2>수동 조작</h2>
          <p className="hint">
            동작 전에 주변을 확인하세요. 위험한 조작은 인터록으로 막히고 이유가 표시됩니다.
            모든 조작은 로그에 기록됩니다.
          </p>
        </div>
        <div className="manual-ready">
          <span className={`lamp ${notReady.length ? "lamp-warn" : "lamp-ok"}`} />
          {notReady.length ? `자동 운전 원위치 아님 (${notReady.length}개)` : "자동 운전 원위치"}
          <button className="btn" onClick={() => run(() => api.homeAll())}>
            전체 원위치
          </button>
        </div>
      </section>

      <div className="manual-grid">
        {UNITS.map((unit) => {
          const devices = manual.devices.filter((d) => d.unit === unit);
          const axes = manual.axes.filter((a) => a.unit === unit);
          return (
            <section key={unit} className="panel">
              <h2>{STATION_LABEL[unit] ?? unit}</h2>
              {devices.map((d) => (
                <DeviceRow key={d.id} d={d} run={run} />
              ))}
              {axes.map((a) => (
                <AxisCard key={a.id} a={a} run={run} />
              ))}
            </section>
          );
        })}
      </div>
    </div>
  );
}

function Lamp({ on, label, tone = "ok" }) {
  return (
    <span className="sensor">
      <span className={`lamp ${on ? `lamp-${tone}` : ""}`} />
      {label}
    </span>
  );
}

function DeviceRow({ d, run }) {
  const label = DEVICE_LABEL[d.id] ?? { name: d.id, off: "OFF", on: "ON" };
  const moving = d.position !== d.target;
  return (
    <div className="device-row">
      <span className="device-name">{label.name}</span>
      <div className="segmented">
        <button className={d.target === 0 ? "active" : ""} onClick={() => run(() => api.device(d.id, false))}>
          {label.off}
        </button>
        <button className={d.target === 1 ? "active" : ""} onClick={() => run(() => api.device(d.id, true))}>
          {label.on}
        </button>
      </div>
      <div className="device-sensors">
        {d.kind === "cylinder" && (
          <>
            <Lamp on={d.home_sensor} label={label.off} />
            <Lamp on={d.work_sensor} label={label.on} />
            {moving && <span className="tag warn">동작 중</span>}
          </>
        )}
        {d.kind === "vacuum" && (
          <>
            <span className="mono">{(d.kpa ?? 0).toFixed(1)} kPa</span>
            <Lamp on={(d.kpa ?? 0) <= VACUUM_OK_KPA} label="진공 스위치" />
          </>
        )}
        {d.kind === "belt" && <Lamp on={d.position >= 1} label="구동" />}
      </div>
    </div>
  );
}

function AxisCard({ a, run }) {
  const pct = ((a.position - a.min) / (a.max - a.min)) * 100;
  return (
    <div className="axis-card">
      <div className="axis-head">
        <strong>{AXIS_LABEL[a.id] ?? a.id}</strong>
        <span className="mono axis-pos">{a.position.toFixed(2)} mm</span>
        {a.moving && <span className="tag warn">이동 중 → {a.target.toFixed(2)}</span>}
      </div>
      <div className="axis-track" aria-hidden>
        <div className="axis-marker" style={{ left: `${pct}%` }} />
      </div>
      <div className="axis-range mono">
        <span>{a.min}</span>
        <span>{a.max}</span>
      </div>
      <div className="axis-buttons">
        {JOGS.map((mm) => (
          <button key={mm} className="maint" onClick={() => run(() => api.jog(a.id, mm))}>
            {mm > 0 ? `+${mm}` : mm}
          </button>
        ))}
      </div>
      <div className="axis-buttons">
        {Object.keys(a.presets).map((p) => (
          <button key={p} className="maint" onClick={() => run(() => api.preset(a.id, p))}>
            {PRESET_LABEL[p] ?? p}
          </button>
        ))}
      </div>
    </div>
  );
}
