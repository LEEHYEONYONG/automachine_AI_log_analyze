import type { MachineState } from "../types";
import { AlarmBanner, AlarmHistory } from "./AlarmPanel";
import { ControlPanel } from "./ControlPanel";
import { ProductionPanel } from "./ProductionPanel";
import { SensorPanel } from "./SensorPanel";
import { StationFlow } from "./StationFlow";
import { TrendPanel } from "./TrendPanel";

interface Props {
  state: MachineState;
  run: (action: () => Promise<void>) => void;
}

export function HmiPage({ state, run }: Props) {
  return (
    <main className="hmi">
      <AlarmBanner alarm={state.alarm} />
      <StationFlow stations={state.stations} />
      <div className="hmi-grid">
        <ControlPanel state={state} run={run} />
        <ProductionPanel state={state} />
        <SensorPanel sensors={state.sensors} />
      </div>
      <TrendPanel />
      <AlarmHistory history={state.alarm_history} />
    </main>
  );
}
