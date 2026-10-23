import { MODE_LABEL, OPERATOR_PHASE_LABEL } from "../labels";
import type { MachineState } from "../types";

/** Machine status line shown at the top of every screen. */
export function Header({ state }: { state: MachineState }) {
  return (
    <header className="header">
      <div className="header-id">
        <span className="machine-id">{state.machine_id}</span>
        <span className="muted">{state.recipe}</span>
        <span className="muted">LOT {state.lot ?? "-"}</span>
      </div>

      <div className={`mode-badge mode-${state.mode}`}>{MODE_LABEL[state.mode]}</div>
      <span className={`opmode-badge opmode-${state.op_mode}`}>{state.op_mode}</span>
      {state.cycle_stop && <span className="tag warn">사이클 정지 중</span>}

      <div className="header-status">
        <span className="mono">{state.time}</span>
        {state.sim.auto_operator && (
          <span className="muted">
            작업자 {state.operator.crew.join("·")} · {OPERATOR_PHASE_LABEL[state.operator.phase] ?? state.operator.phase}
          </span>
        )}
      </div>
    </header>
  );
}
