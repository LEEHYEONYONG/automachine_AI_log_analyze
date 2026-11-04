import { MODE_LABEL, OPERATOR_PHASE_LABEL } from "../labels";

import { INIT_STEP_LABEL } from "./hmiLabels";
import { LoginControl } from "./LoginControl";
import { useT } from "../prefs";

/** Machine status line shown at the top of every screen. */
export function Header({ state, run }) {
  const t = useT();
  const test = state.run.mode !== "PRODUCTION";
  return (
    <header className="header">
      <div className="header-id">
        <span className="machine-id">{state.machine_id}</span>
        <span className="muted">{state.recipe}</span>
        <span className="muted">LOT {state.lot ?? "-"}</span>
      </div>

      <div className={`mode-badge mode-${state.mode}`}>{t(MODE_LABEL[state.mode])}</div>
      {test && (
        <span className="tag run-mode-tag" title={t("설정 > 운전에서 바꿉니다")}>
          {state.run.mode === "DRY" ? "DRY RUN" : "DUMMY RUN"}
          {state.run.mode === "DUMMY" && ` ${state.run.dummy_fed}/${state.run.dummy_count}`}
          {state.run.mode === "DRY" && state.run.dry_no_motion && ` · ${t("기구 동작 끔")}`}
        </span>
      )}
      <span className={`opmode-badge opmode-${state.op_mode}`}>{state.op_mode}</span>
      {state.safety.estop && <span className="tag danger">{t("비상정지")}</span>}
      {Object.entries(state.safety.doors_open)
        .filter(([, open]) => open)
        .map(([door]) => (
          <span key={door} className="tag danger">
            {t("도어 열림")} {door === "FRONT_LEFT" ? t("(좌)") : t("(우)")}
          </span>
        ))}
      {state.init.state === "REQUIRED" && <span className="tag warn">{t("원점 복귀 필요")}</span>}
      {state.init.state === "RUNNING" && (
        <span className="tag warn">{t("원점 복귀 중")} · {t(INIT_STEP_LABEL[state.init.step] ?? state.init.step)}</span>
      )}
      {state.cycle_stop && <span className="tag warn">{t("사이클 정지 중")}</span>}

      <div className="header-status">
        <span className="mono">{state.time}</span>
        <LoginControl state={state} run={run} />
        {state.sim.auto_operator && (
          <span className="muted">
            {t("작업자")} {state.operator.crew.join("·")} · {t(OPERATOR_PHASE_LABEL[state.operator.phase] ?? state.operator.phase)}
          </span>
        )}
      </div>
    </header>
  );
}
