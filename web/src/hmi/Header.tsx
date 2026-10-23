import { api } from "../api";
import { MODE_LABEL } from "../labels";
import type { MachineState } from "../types";

const SPEEDS = [1, 10, 60, 300];

interface Props {
  state: MachineState;
  connected: boolean;
  run: (action: () => Promise<void>) => void;
}

export function Header({ state, connected, run }: Props) {
  const { sim } = state;
  return (
    <header className="header">
      <div className="header-id">
        <span className="machine-id">{state.machine_id}</span>
        <span className="muted">{state.recipe}</span>
        <span className="muted">LOT {state.lot ?? "-"}</span>
      </div>

      <div className={`mode-badge mode-${state.mode}`}>{MODE_LABEL[state.mode]}</div>

      <div className="header-time">
        <span className={`conn ${connected ? "on" : "off"}`} title={connected ? "서버 연결됨" : "서버 연결 끊김"} />
        <span className="mono">{state.time}</span>
      </div>

      <div className="header-controls">
        <div className="segmented" role="group" aria-label="시뮬레이션 배속">
          {SPEEDS.map((s) => (
            <button
              key={s}
              className={sim.speed === s ? "active" : ""}
              onClick={() => run(() => api.setSim({ speed: s }))}
            >
              ×{s}
            </button>
          ))}
          <button
            className={sim.paused ? "active" : ""}
            onClick={() => run(() => api.setSim({ paused: !sim.paused }))}
          >
            {sim.paused ? "재개" : "일시정지"}
          </button>
        </div>
        <label className="toggle" title="켜면 가상 작업자가 알람에 자동으로 대응합니다">
          <input
            type="checkbox"
            checked={sim.auto_operator}
            onChange={(e) => run(() => api.setAutoOperator(e.target.checked))}
          />
          자동 작업자
        </label>
      </div>
    </header>
  );
}
