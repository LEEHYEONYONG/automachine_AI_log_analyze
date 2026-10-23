import { api } from "../api";
import { ACTION_LABEL, MAINTENANCE_ACTIONS } from "../labels";
import type { MachineState } from "../types";

interface Props {
  state: MachineState;
  run: (action: () => Promise<void>) => void;
}

export function ControlPanel({ state, run }: Props) {
  const running = state.mode === "RUNNING";
  return (
    <section className="panel">
      <h2>운전 조작</h2>
      <div className="op-buttons">
        <button className="op op-start" disabled={state.mode !== "STOPPED"} onClick={() => run(() => api.command("start"))}>
          START
        </button>
        <button className="op op-stop" disabled={!running} onClick={() => run(() => api.command("stop"))}>
          STOP
        </button>
        <button className="op op-reset" disabled={state.mode !== "ALARM"} onClick={() => run(() => api.command("reset"))}>
          RESET
        </button>
      </div>

      <h3>유지보수 조치</h3>
      <p className="hint">{running ? "조치하려면 먼저 장비를 정지하세요." : "조치 후 RESET → START 순서로 재가동합니다."}</p>
      <div className="maint-grid">
        {MAINTENANCE_ACTIONS.map((a) => (
          <button key={a} className="maint" disabled={running} onClick={() => run(() => api.maintenance(a))}>
            {ACTION_LABEL[a]}
          </button>
        ))}
      </div>
    </section>
  );
}
