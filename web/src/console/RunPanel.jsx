import { tr } from "../prefs";
import { useState } from "react";
import { api } from "../api";
import { SCENARIO_LABEL } from "../labels";

const LIVE = "";

export function RunPanel({ state, scenarios, recipes, run }) {
  const [scenario, setScenario] = useState(LIVE);
  const others = recipes.filter((r) => r !== state.recipe);
  const [recipe, setRecipe] = useState("");
  const target = others.includes(recipe) ? recipe : others[0] ?? "";

  const startNewRun = () => {
    const name = scenario ? SCENARIO_LABEL[scenario] ?? scenario : tr("고장 없는 실시간 실행");
    if (window.confirm(tr("현재 실행을 종료하고 '{a}'(으)로 새 실행을 시작할까요?", { a: name }))) {
      run(() => api.newRun(scenario || null));
    }
  };

  return (
    <section className="panel">
      <h2>{tr("실행 관리")}</h2>
      <dl className="kv">
        <dt>{tr("실행 ID")}</dt>
        <dd className="mono">{state.sim.run_id}</dd>
        <dt>{tr("시나리오")}</dt>
        <dd>{SCENARIO_LABEL[state.sim.scenario] ?? state.sim.scenario}</dd>
        <dt>{tr("정답 파일")}</dt>
        <dd className="mono small">{state.engineer.truth_file}</dd>
      </dl>

      <h3>{tr("새 실행")}</h3>
      <div className="form-row">
        <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
          <option value={LIVE}>{tr("실시간 실행 (고장 없음)")}</option>
          {scenarios.map((s) => (
            <option key={s} value={s}>
              {SCENARIO_LABEL[s] ?? s}
            </option>
          ))}
        </select>
        <button className="btn" onClick={startNewRun}>
          {tr("새 실행 시작")}
        </button>
      </div>
      <p className="hint">{tr("시나리오의 고장은 실행 시작 시점 기준으로 예약됩니다. 새 실행은 정지 상태로 시작합니다.")}</p>

      <h3>{tr("모델 체인지")}</h3>
      <div className="form-row">
        <select value={target} onChange={(e) => setRecipe(e.target.value)} disabled={others.length === 0}>
          {others.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <button className="btn" disabled={!target} onClick={() => run(() => api.changeRecipe(target))}>
          {tr("모델 체인지")}
        </button>
      </div>
      <p className="hint">
        {state.sim.auto_operator
          ? tr("자동 작업자가 사이클 정지 후 15~25분 동안 셋업합니다. 레시피 오입력이나 위치 오차가 생길 수 있습니다.")
          : tr("장비가 정지 상태일 때 바로 바뀝니다.")}
      </p>
    </section>
  );
}
