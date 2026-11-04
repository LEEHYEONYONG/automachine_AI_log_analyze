import { tr } from "../prefs";
import { useMeta } from "../api";

import { FaultInjectPanel } from "./FaultInjectPanel";
import { FieldPanel } from "./FieldPanel";
import { FaultList } from "./FaultList";
import { HiddenStatePanel } from "./HiddenStatePanel";
import { RunPanel } from "./RunPanel";

export function ConsolePage({ state, run }) {
  const meta = useMeta();
  return (
    <main className="console">
      <div className="console-notice">
        {tr("엔지니어 전용 화면입니다. 고장 정답과 실제 물리 상태가 보이므로, AI 분석 결과는 이 화면을 보기 전에 기록해 두세요.")}
      </div>
      <div className="console-grid">
        <div className="col">
          <RunPanel state={state} scenarios={meta?.scenarios ?? []} recipes={meta?.recipes ?? []} run={run} />
          <FieldPanel state={state} run={run} />
          {meta && <FaultInjectPanel faultTypes={meta.fault_types} run={run} />}
        </div>
        <div className="col">
          <HiddenStatePanel
            hidden={state.engineer.hidden}
            sensors={state.sensors}
            setpointErrors={state.engineer.setpoint_errors}
          />
          <FaultList faults={state.engineer.faults} />
        </div>
      </div>
    </main>
  );
}
