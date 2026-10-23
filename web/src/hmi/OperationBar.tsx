import { useState } from "react";
import { api } from "../api";
import type { MachineState } from "../types";

interface Props {
  state: MachineState;
  run: (action: () => Promise<void>) => void;
}

/** Mode switch and run buttons that stay at the bottom of every HMI screen, like the keys under a real panel. */
export function OperationBar({ state, run }: Props) {
  const [askWip, setAskWip] = useState(false);
  const running = state.mode === "RUNNING";
  const auto = state.op_mode === "AUTO";
  const initializing = state.init.state === "RUNNING";
  const canInit = auto && state.mode === "STOPPED" && !initializing;
  const wip = state.stations.filter((s) => s.wp).length;
  const can = state.hmi.permissions;
  const needLogin = "권한이 없습니다. 로그인하세요";

  const initialize = (clearParts: boolean) => {
    setAskWip(false);
    run(() => api.initialize(clearParts));
  };

  const startBlocked = !can.start
    ? needLogin
    : !auto
    ? "MANUAL 모드에서는 START할 수 없습니다"
    : state.init.state !== "DONE"
      ? "원점 복귀를 먼저 하세요"
      : "";

  return (
    <div className="op-bar">
      <button
        className={`estop ${state.safety.estop ? "pressed" : ""}`}
        title={state.safety.estop ? "비상정지 버튼을 돌려서 해제합니다" : "누르면 모든 동작이 즉시 정지합니다"}
        onClick={() => run(() => api.estop(!state.safety.estop))}
      >
        {state.safety.estop ? "비상정지 해제" : "비상정지"}
      </button>
      <div className="mode-switch" role="radiogroup" aria-label="운전 모드">
        {(["AUTO", "MANUAL"] as const).map((m) => (
          <button
            key={m}
            role="radio"
            aria-checked={state.op_mode === m}
            className={state.op_mode === m ? `active mode-${m}` : ""}
            disabled={(running && m === "MANUAL") || initializing || !can.op_mode}
            title={can.op_mode ? "" : "엔지니어 이상 권한이 필요합니다"}
            onClick={() => run(() => api.setOpMode(m))}
          >
            {m}
          </button>
        ))}
      </div>
      <button
        className={`op op-init ${state.init.state === "REQUIRED" ? "attention" : ""}`}
        disabled={!canInit || !can.initialize}
        title={can.initialize ? "실린더와 축을 원점으로 보내고 재공품을 확인합니다" : needLogin}
        onClick={() => (wip ? setAskWip(true) : initialize(false))}
      >
        {initializing ? `원점 복귀 중 ${Math.round(state.init.progress * 100)}%` : "원점 복귀"}
      </button>
      <button
        className="op op-start"
        disabled={state.mode !== "STOPPED" || !!startBlocked}
        title={startBlocked}
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
      <button
        className="op op-reset"
        disabled={state.mode !== "ALARM" || !can.reset}
        title={can.reset ? "" : needLogin}
        onClick={() => run(() => api.command("reset"))}>
        RESET
      </button>

      {askWip && (
        <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-labelledby="wip-title">
          <div className="dialog">
            <h2 id="wip-title">라인에 제품 {wip}개가 남아 있습니다</h2>
            <p className="hint">원점 복귀 후 재공품을 어떻게 처리할까요?</p>
            <button className="dialog-option" onClick={() => initialize(false)}>
              <strong>재공품 유지</strong>
              <span>작업 도중이던 스테이션은 처음부터 다시 합니다. 도포가 이미 시작된 제품은 NG로 판정해 NG 버퍼로 보냅니다.</span>
            </button>
            <button className="dialog-option" onClick={() => initialize(true)}>
              <strong>재공품 제거</strong>
              <span>작업자가 라인의 제품을 모두 꺼낸 것으로 처리합니다 (생산 기록에 SCRAP_INIT로 남음).</span>
            </button>
            <button className="btn-text" onClick={() => setAskWip(false)}>
              취소
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
