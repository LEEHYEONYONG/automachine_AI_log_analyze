import { Canvas } from "@react-three/fiber";
import { MODE_LABEL } from "../labels";
import type { MachineState } from "../types";
import { Scene } from "./Scene";

export default function ViewerPage({ state }: { state: MachineState }) {
  const fast = state.sim.speed > 10;
  return (
    <main className="viewer">
      <Canvas shadows camera={{ position: [1.5, 5.5, 8.5], fov: 40 }} dpr={[1, 2]}>
        <Scene state={state} />
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
      <div className="viewer-help">드래그: 회전 · 휠: 확대/축소 · 우클릭 드래그: 이동</div>
    </main>
  );
}
