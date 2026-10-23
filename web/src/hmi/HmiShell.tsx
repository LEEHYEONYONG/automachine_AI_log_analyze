import type { MachineState } from "../types";
import { AlarmBanner } from "./AlarmPanel";
import { OperationBar } from "./OperationBar";
import { AlarmPage } from "./pages/AlarmPage";
import { LogPage } from "./pages/LogPage";
import { MainPage } from "./pages/MainPage";
import { MaintenancePage } from "./pages/MaintenancePage";
import { ProductionPage } from "./pages/ProductionPage";
import { SequencePage } from "./pages/SequencePage";

const PAGES = [
  { id: "main", label: "메인" },
  { id: "sequence", label: "시퀀스" },
  { id: "alarm", label: "알람" },
  { id: "log", label: "로그" },
  { id: "production", label: "생산" },
  { id: "maintenance", label: "유지보수" },
] as const;

export type HmiPage = (typeof PAGES)[number]["id"];

export const isHmiPage = (p: string | undefined): p is HmiPage => PAGES.some((x) => x.id === p);

interface Props {
  state: MachineState;
  page: HmiPage;
  onPage: (page: HmiPage) => void;
  run: (action: () => Promise<void>) => void;
}

/** Operator panel: menu on the left, the selected screen, and the run buttons fixed at the bottom. */
export function HmiShell({ state, page, onPage, run }: Props) {
  return (
    <div className="hmi-shell">
      <nav className="hmi-nav" aria-label="HMI 메뉴">
        {PAGES.map((p) => (
          <button key={p.id} className={page === p.id ? "active" : ""} onClick={() => onPage(p.id)}>
            {p.label}
            {p.id === "alarm" && state.alarm && <span className="nav-dot" aria-label="알람 발생 중" />}
          </button>
        ))}
      </nav>
      <main className="hmi-content">
        <AlarmBanner alarm={state.alarm} onClick={() => onPage("alarm")} />
        {page === "main" && <MainPage state={state} onPage={onPage} />}
        {page === "sequence" && <SequencePage state={state} />}
        {page === "alarm" && <AlarmPage state={state} />}
        {page === "log" && <LogPage />}
        {page === "production" && <ProductionPage state={state} />}
        {page === "maintenance" && <MaintenancePage state={state} run={run} />}
      </main>
      <OperationBar state={state} run={run} />
    </div>
  );
}
