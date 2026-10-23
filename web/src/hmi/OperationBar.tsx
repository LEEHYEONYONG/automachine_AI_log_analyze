import { api } from "../api";
import type { MachineState } from "../types";

interface Props {
  state: MachineState;
  run: (action: () => Promise<void>) => void;
}

/** Run buttons that stay at the bottom of every HMI screen, like the hard keys under a real panel. */
export function OperationBar({ state, run }: Props) {
  const running = state.mode === "RUNNING";
  return (
    <div className="op-bar">
      <button className="op op-start" disabled={state.mode !== "STOPPED"} onClick={() => run(() => api.command("start"))}>
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
