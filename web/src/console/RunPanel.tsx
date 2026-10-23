import { useState } from "react";
import { api } from "../api";
import { SCENARIO_LABEL } from "../labels";
import type { MachineState } from "../types";

interface Props {
  state: MachineState;
  scenarios: string[];
  run: (action: () => Promise<void>) => void;
}

const LIVE = "";

export function RunPanel({ state, scenarios, run }: Props) {
  const [scenario, setScenario] = useState(LIVE);

  const startNewRun = () => {
    const name = scenario ? SCENARIO_LABEL[scenario] ?? scenario : "고장 없는 실시간 실행";
    if (window.confirm(`현재 실행을 종료하고 '${name}'(으)로 새 실행을 시작할까요?`)) {
      run(() => api.newRun(scenario || null));
    }
  };

  return (
    <section className="panel">
      <h2>실행 관리</h2>
      <dl className="kv">
        <dt>실행 ID</dt>
        <dd className="mono">{state.sim.run_id}</dd>
        <dt>시나리오</dt>
        <dd>{SCENARIO_LABEL[state.sim.scenario] ?? state.sim.scenario}</dd>
        <dt>정답 파일</dt>
        <dd className="mono small">{state.engineer.truth_file}</dd>
      </dl>

      <h3>새 실행</h3>
      <div className="form-row">
        <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
          <option value={LIVE}>실시간 실행 (고장 없음)</option>
          {scenarios.map((s) => (
            <option key={s} value={s}>
              {SCENARIO_LABEL[s] ?? s}
            </option>
          ))}
        </select>
        <button className="btn" onClick={startNewRun}>
          새 실행 시작
        </button>
      </div>
      <p className="hint">시나리오의 고장은 실행 시작 시점 기준으로 예약됩니다. 새 실행은 정지 상태로 시작합니다.</p>
    </section>
  );
}
