import { AlarmBanner } from "./AlarmPanel";
import { OperationBar } from "./OperationBar";
import { AlarmPage } from "./pages/AlarmPage";
import { IoPage } from "./pages/IoPage";
import { LogPage } from "./pages/LogPage";
import { MainPage } from "./pages/MainPage";
import { MaintenancePage } from "./pages/MaintenancePage";
import { ManualPage } from "./pages/ManualPage";
import { ProductionPage } from "./pages/ProductionPage";
import { RecipePage } from "./pages/RecipePage";
import { SequencePage } from "./pages/SequencePage";
import { SettingsPage } from "./pages/SettingsPage";
import { PAGES } from "./hmiPages";
import { useT } from "../prefs";

/** Operator panel: menu on the left, the selected screen, and the run buttons fixed at the bottom. */
export function HmiShell({ state, page, onPage, run }) {
  const t = useT();
  return (
    <div className="hmi-shell">
      <nav className="hmi-nav" aria-label={t("HMI 메뉴")}>
        {PAGES.map((p) => (
          <button key={p.id} className={page === p.id ? "active" : ""} onClick={() => onPage(p.id)}>
            {t(p.label)}
            {p.id === "alarm" && state.alarm && <span className="nav-dot" aria-label={t("알람 발생 중")} />}
          </button>
        ))}
      </nav>
      <main className="hmi-content">
        <AlarmBanner alarm={state.alarm} onClick={() => onPage("alarm")} />
        {page === "main" && <MainPage state={state} onPage={onPage} />}
        {page === "sequence" && <SequencePage state={state} />}
        {page === "manual" && <ManualPage state={state} run={run} />}
        {page === "io" && <IoPage state={state} run={run} />}
        {page === "alarm" && <AlarmPage state={state} />}
        {page === "log" && <LogPage />}
        {page === "production" && <ProductionPage state={state} />}
        {page === "recipe" && <RecipePage state={state} run={run} />}
        {page === "maintenance" && <MaintenancePage state={state} run={run} />}
        {page === "settings" && <SettingsPage state={state} />}
      </main>
      <OperationBar state={state} run={run} />
    </div>
  );
}
