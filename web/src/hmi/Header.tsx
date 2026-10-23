import { MODE_LABEL, OPERATOR_PHASE_LABEL } from "../labels";
import type { MachineState } from "../types";
import { INIT_STEP_LABEL } from "./hmiLabels";
import { LoginControl } from "./LoginControl";

/** Machine status line shown at the top of every screen. */
export function Header({ state, run }: { state: MachineState; run: (action: () => Promise<void>) => void }) {
  return (
    <header className="header">
      <div className="header-id">
        <span className="machine-id">{state.machine_id}</span>
        <span className="muted">{state.recipe}</span>
        <span className="muted">LOT {state.lot ?? "-"}</span>
      </div>

      <div className={`mode-badge mode-${state.mode}`}>{MODE_LABEL[state.mode]}</div>
      <span className={`opmode-badge opmode-${state.op_mode}`}>{state.op_mode}</span>
      {state.safety.estop && <span className="tag danger">비상정지</span>}
      {Object.entries(state.safety.doors_open)
        .filter(([, open]) => open)
        .map(([door]) => (
          <span key={door} className="tag danger">
            도어 열림 {door === "FRONT_LEFT" ? "(좌)" : "(우)"}
          </span>
        ))}
      {state.init.state === "REQUIRED" && <span className="tag warn">원점 복귀 필요</span>}
      {state.init.state === "RUNNING" && (
        <span className="tag warn">원점 복귀 중 · {INIT_STEP_LABEL[state.init.step] ?? state.init.step}</span>
      )}
      {state.cycle_stop && <span className="tag warn">사이클 정지 중</span>}

      <div className="header-status">
        <span className="mono">{state.time}</span>
        <LoginControl state={state} run={run} />
        {state.sim.auto_operator && (
          <span className="muted">
            작업자 {state.operator.crew.join("·")} · {OPERATOR_PHASE_LABEL[state.operator.phase] ?? state.operator.phase}
          </span>
        )}
      </div>
    </header>
  );
}
