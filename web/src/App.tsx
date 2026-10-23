import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { useMachineState } from "./api";
import { ConsolePage } from "./console/ConsolePage";
import { Header } from "./hmi/Header";
import { HmiShell, isHmiPage, type HmiPage } from "./hmi/HmiShell";
import { SimBar } from "./SimBar";

// three.js is large, so the viewer is only downloaded when its tab is opened.
const ViewerPage = lazy(() => import("./viewer/ViewerPage"));

type Tab = "hmi" | "console" | "3d";

const TABS: { id: Tab; label: string }[] = [
  { id: "hmi", label: "HMI" },
  { id: "console", label: "엔지니어 콘솔" },
  { id: "3d", label: "3D 뷰어" },
];

// The location hash holds the screen (#hmi/sequence, #console, #3d) so reloads and links keep it.
function readHash(): { tab: Tab; page: HmiPage } {
  const [tab, page] = location.hash.slice(1).split("/");
  return {
    tab: TABS.some((t) => t.id === tab) ? (tab as Tab) : "hmi",
    page: isHmiPage(page) ? page : "main",
  };
}

export default function App() {
  const { state, connected } = useMachineState();
  const [route, setRoute] = useState(readHash);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onHash = () => setRoute(readHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (tab: Tab, page: HmiPage = route.page) => {
    location.hash = tab === "hmi" ? `hmi/${page}` : tab;
  };

  const run = useCallback((action: () => Promise<void>) => {
    action().catch((e: Error) => {
      setError(e.message);
      window.setTimeout(() => setError(null), 4000);
    });
  }, []);

  if (!state) {
    return <div className="loading">서버 연결 중… (python -m server 실행 여부를 확인하세요)</div>;
  }

  return (
    <div className="app">
      <div className="topbar">
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.id} className={route.tab === t.id ? "active" : ""} onClick={() => go(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
        <SimBar state={state} connected={connected} run={run} />
      </div>
      <Header state={state} run={run} />
      {route.tab === "hmi" && <HmiShell state={state} page={route.page} onPage={(p) => go("hmi", p)} run={run} />}
      {route.tab === "console" && <ConsolePage state={state} run={run} />}
      {route.tab === "3d" && (
        <Suspense fallback={<div className="loading">3D 뷰어 불러오는 중…</div>}>
          <ViewerPage state={state} />
        </Suspense>
      )}
      {error && <div className="toast">{error}</div>}
    </div>
  );
}
