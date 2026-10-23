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
      <StationFlow stations={state.stations} onSelect={(name) => (location.hash = `hmi/sequence/${name}`)} />
      <div className="main-grid">
        <ProductionPanel state={state} />
        <SensorPanel sensors={state.sensors} />
      </div>
      <LiveLog entries={state.live_log} onMore={() => onPage("log")} />
    </div>
  );
}
