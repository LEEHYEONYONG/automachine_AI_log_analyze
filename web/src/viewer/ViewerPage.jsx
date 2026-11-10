import { tr } from "../prefs";
import { Canvas } from "@react-three/fiber";
import { useState } from "react";
import { time } from "../analysis/evidence";
import { useWatch } from "../analysis/useWatch";
import { MODE_LABEL } from "../labels";
import { usePrefs } from "../prefs";

import { activeFault, DEVICE_LABEL } from "./faults";
import { VIEWS } from "./layout";
import { Scene } from "./Scene";

// ?view=dispenser opens straight into a preset, e.g. for a shared link or a screenshot.
function initialView() {
  const v = new URLSearchParams(location.search).get("view");
  return v && v in VIEWS ? v : "overview";
}

// ?fault=needle previews a highlight without a live alert (checking the marker, screenshots).
function previewFault() {
  const d = new URLSearchParams(location.search).get("fault");
  return d && d in DEVICE_LABEL ? { device: d, alert: { cause_label: tr("미리보기"), started_at: null } } : null;
}

// The controller sits behind the station, so the dispenser close-up would not show it.
const CLOSE_UP = { needle: "dispenser", syringe: "dispenser", fixture: "dispenser", controller: "overview" };

/** A dry run has no parts on the line, and with motion off nothing moves either. */
function shownState(state) {
  if (state.run?.mode !== "DRY") return state;
  const still = state.run.dry_no_motion;
  return {
    ...state,
    stations: state.stations.map((s) => ({ ...s, wp: null, ...(still ? { step: "", progress: 0 } : {}) })),
  };
}

export default function ViewerPage({ state: live }) {
  const state = shownState(live);
  const { prefs } = usePrefs();
  const [covers, setCovers] = useState(true);
  const [effects, setEffects] = useState(prefs.viewerEffects);
  const [view, setView] = useState(initialView);
  const [highlight, setHighlight] = useState(true);
  const watch = useWatch();
  const found = activeFault(watch) ?? previewFault();
  const fault = highlight ? found : null;
  const fast = state.sim.speed > 10;
  const start = VIEWS[view].position;
  return (
    <main className="viewer">
      <Canvas shadows camera={{ position: [...start], fov: 40 }} dpr={[1, 2]}>
        <Scene state={state} covers={covers} view={view} effects={effects} fault={fault} />
      </Canvas>

      <div className="viewer-overlay">
        <div className={`mode-badge mode-${state.mode}`}>{MODE_LABEL[state.mode]}</div>
        {state.alarm && (
          <div className="viewer-alarm">
            <span className="alarm-code">{state.alarm.code}</span> {state.alarm.text}
          </div>
        )}
        {fault && (
          <div className="viewer-fault">
            <span className="live-bar-tag">{tr("AI 예측 경보")}</span>
            {fault.alert.started_at && <span className="mono">{time(fault.alert.started_at)}</span>}
            <strong>{fault.alert.cause_label}</strong>
            <span>→ {DEVICE_LABEL[fault.device]}</span>
            {view !== CLOSE_UP[fault.device] && (
              <button className="btn-text" onClick={() => setView(CLOSE_UP[fault.device])}>
                {tr("장치 보기")}
              </button>
            )}
          </div>
        )}
        {fast && <div className="hint">{tr("배속이 높으면 동작이 건너뛰어 보입니다. ×1~×10에서 자연스럽게 보입니다.")}</div>}
      </div>
      <div className="viewer-tools">
        <div className="segmented" role="group" aria-label={tr("시점")}>
          {(Object.keys(VIEWS) ).map((v) => (
            <button key={v} className={view === v ? "active" : ""} onClick={() => setView(v)}>
              {tr(VIEWS[v].label)}
            </button>
          ))}
        </div>
        <label className="toggle">
          <input type="checkbox" checked={covers} onChange={(e) => setCovers(e.target.checked)} />
          {tr("안전 커버")}
        </label>
        <label className="toggle" title={tr("실시간 감시의 최근 경보가 가리키는 장치를 빨갛게 표시합니다")}>
          <input type="checkbox" checked={highlight} onChange={(e) => setHighlight(e.target.checked)} />
          {tr("AI 고장 강조")}
        </label>
        <label className="toggle" title={tr("느리면 끄세요")}>
          <input type="checkbox" checked={effects} onChange={(e) => setEffects(e.target.checked)} />
          {tr("그래픽 효과")}
        </label>
      </div>
      <div className="viewer-help">{tr("드래그: 회전 · 휠: 확대/축소 · 우클릭 드래그: 이동")}</div>
    </main>
  );
}
