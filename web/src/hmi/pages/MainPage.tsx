import type { MachineState } from "../../types";
import type { HmiPage } from "../HmiShell";
import { LiveLog } from "../LiveLog";
import { ProductionPanel } from "../ProductionPanel";
import { SensorPanel } from "../SensorPanel";
import { StationFlow } from "../StationFlow";

/** The screen the operator watches during production. */
export function MainPage({ state, onPage }: { state: MachineState; onPage: (p: HmiPage) => void }) {
  return (
    <div className="page">
      {state.init.state === "REQUIRED" && state.op_mode === "AUTO" && (
        <p className="notice notice-warn">
          원점 복귀가 필요합니다. 하단의 [원점 복귀]를 누른 뒤 START하세요. (전원 투입 후, 또는 MANUAL에서 장치를 움직인 뒤)
        </p>
      )}
      <StationFlow stations={state.stations} onSelect={(name) => (location.hash = `hmi/sequence/${name}`)} />
      <div className="main-grid">
        <ProductionPanel state={state} />
        <SensorPanel sensors={state.sensors} />
      </div>
      <LiveLog entries={state.live_log} onMore={() => onPage("log")} />
    </div>
  );
}
