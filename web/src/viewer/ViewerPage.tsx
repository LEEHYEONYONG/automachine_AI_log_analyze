import { Canvas } from "@react-three/fiber";
import { useState } from "react";
import { MODE_LABEL } from "../labels";
import type { MachineState } from "../types";
import { VIEWS, type ViewName } from "./CameraRig";
import { Scene } from "./Scene";

// ?view=dispenser opens straight into a preset, e.g. for a shared link or a screenshot.
function initialView(): ViewName {
  const v = new URLSearchParams(location.search).get("view");
  return v && v in VIEWS ? (v as ViewName) : "overview";
}

export default function ViewerPage({ state }: { state: MachineState }) {
  const [covers, setCovers] = useState(true);
  const [view, setView] = useState<ViewName>(initialView);
  const fast = state.sim.speed > 10;
  const start = VIEWS[view].position;
  return (
    <main className="viewer">
      <Canvas shadows camera={{ position: [...start], fov: 40 }} dpr={[1, 2]}>
        <Scene state={state} covers={covers} view={view} />
      </Canvas>

      <div className="viewer-overlay">
        <div className={`mode-badge mode-${state.mode}`}>{MODE_LABEL[state.mode]}</div>
        {state.alarm && (
          <div className="viewer-alarm">
            <span className="alarm-code">{state.alarm.code}</span> {state.alarm.text}
          </div>
        )}
        {fast && <div className="hint">배속이 높으면 동작이 건너뛰어 보입니다. ×1~×10에서 자연스럽게 보입니다.</div>}
      </div>
      <div className="viewer-tools">
        <div className="segmented" role="group" aria-label="시점">
          {(Object.keys(VIEWS) as ViewName[]).map((v) => (
            <button key={v} className={view === v ? "active" : ""} onClick={() => setView(v)}>
              {VIEWS[v].label}
            </button>
          ))}
        </div>
        <label className="toggle">
          <input type="checkbox" checked={covers} onChange={(e) => setCovers(e.target.checked)} />
          안전 커버
        </label>
      </div>
      <div className="viewer-help">드래그: 회전 · 휠: 확대/축소 · 우클릭 드래그: 이동</div>
    </main>
  );
}
