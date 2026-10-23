import { useCallback, useState } from "react";
import { useMachineState } from "./api";
import { ConsolePage } from "./console/ConsolePage";
import { Header } from "./hmi/Header";
import { HmiPage } from "./hmi/HmiPage";

type Tab = "hmi" | "console" | "3d";

const TABS: { id: Tab; label: string; ready: boolean }[] = [
  { id: "hmi", label: "HMI", ready: true },
  { id: "console", label: "엔지니어 콘솔", ready: true },
  { id: "3d", label: "3D 뷰어", ready: false },
];

export default function App() {
  const { state, connected } = useMachineState();
  const [tab, setTab] = useState<Tab>("hmi");
  const [error, setError] = useState<string | null>(null);

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
      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? "active" : ""}
            disabled={!t.ready}
            onClick={() => setTab(t.id)}
          >
            {t.label}
            {!t.ready && <span className="soon">준비 중</span>}
          </button>
        ))}
      </nav>
      <Header state={state} connected={connected} run={run} />
      {tab === "hmi" && <HmiPage state={state} run={run} />}
      {tab === "console" && <ConsolePage state={state} run={run} />}
      {error && <div className="toast">{error}</div>}
    </div>
  );
}
