import { api } from "../api";
import type { MachineState } from "../types";

interface Props {
  state: MachineState;
  run: (action: () => Promise<void>) => void;
}

/** Mode switch and run buttons that stay at the bottom of every HMI screen, like the keys under a real panel. */
export function OperationBar({ state, run }: Props) {
  const running = state.mode === "RUNNING";
  const auto = state.op_mode === "AUTO";
  return (
    <div className="op-bar">
      <div className="mode-switch" role="radiogroup" aria-label="운전 모드">
        {(["AUTO", "MANUAL"] as const).map((m) => (
          <button
            key={m}
            role="radio"
            aria-checked={state.op_mode === m}
            className={state.op_mode === m ? `active mode-${m}` : ""}
            disabled={running && m === "MANUAL"}
            onClick={() => run(() => api.setOpMode(m))}
          >
            {m}
          </button>
        ))}
      </div>
      <button
        className="op op-start"
        disabled={state.mode !== "STOPPED" || !auto}
        title={auto ? "" : "MANUAL 모드에서는 START할 수 없습니다"}
        onClick={() => run(() => api.command("start"))}
      >
        START
      </button>
      <button
        className="op op-cycle"
        disabled={!running || state.cycle_stop}
        title="라인에 있는 제품을 모두 처리한 뒤 정지합니다"
        onClick={() => run(() => api.command("cycle_stop"))}
      >
        CYCLE STOP
      </button>
      <button className="op op-stop" disabled={!running} title="즉시 정지합니다" onClick={() => run(() => api.command("stop"))}>
        STOP
      </button>
      <button className="op op-reset" disabled={state.mode !== "ALARM"} onClick={() => run(() => api.command("reset"))}>
        RESET
      </button>
    </div>
  );
}
