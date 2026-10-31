import { useEffect, useRef, useState } from "react";

// The operations API only exists on k8s; under Compose this path reaches the simulator, which answers 404.
const API = "/api/ops";
const OVERVIEW_MS = 2000;
const INFRA_MS = 3000;
const WATCH_MS = 500; // while a kill is being followed

const SERVICE_LABEL = {
  web: "웹 화면",
  sim: "시뮬레이터",
  analysis: "AI 분석",
  db: "데이터베이스",
  ops: "운영 API",
  "gpu-metrics": "GPU 수집기",
};

const clock = () => new Date().toTimeString().slice(0, 8);

function age(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  if (seconds < 60) return `${seconds}초`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}분`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}시간`;
  return `${Math.floor(seconds / 86400)}일`;
}

const gib = (mib) => (mib / 1024).toFixed(1);

function statusTone(status, ready, containers) {
  if (status === "Running") return ready === containers ? "ok" : "warn";
  if (status === "Terminating" || status === "Pending" || status === "ContainerCreating" || /^Init:\d/.test(status)) {
    return "warn";
  }
  return "ng";
}

async function fetchJson(path) {
  const res = await fetch(path);
  if (res.status === 403) throw new Error("이 PC 안에서만 볼 수 있습니다.");
  if (res.status === 404) throw new Error("운영 API가 없습니다. k8s로 실행할 때만 쓸 수 있습니다 (http://127.0.0.1).");
  if (!res.ok) throw new Error(`운영 API 응답 ${res.status}`);
  return res.json();
}

/** Calls load every intervalMs (and at once) and keeps the last good answer on screen while a call is in flight. */
function usePolling(path, intervalMs) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetchJson(path)
        .then((d) => {
          if (!cancelled) {
            setData(d);
            setError(null);
          }
        })
        .catch((e) => {
          if (!cancelled) setError(e.message);
        });
    load();
    const timer = window.setInterval(load, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [path, intervalMs]);
  return { data, error };
}

function Meter({ label, used, total, text }) {
  const known = used !== null && used !== undefined && total;
  const pct = known ? Math.min(100, (used / total) * 100) : 0;
  const tone = pct >= 90 ? "ng" : pct >= 70 ? "warn" : "ok";
  return (
    <div className="ops-meter">
      <div className="ops-meter-head">
        <span>{label}</span>
        <span className="mono">{known ? text : "측정 중"}</span>
      </div>
      <div className="ops-bar" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className={`ops-bar-fill ops-${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function InfraPanel({ infra, error }) {
  if (!infra) return <section className="panel"><h2>인프라</h2><p className="hint">{error ?? "불러오는 중…"}</p></section>;
  const { nodes, disk, gpu, ollama } = infra;
  return (
    <section className="panel">
      <h2>인프라</h2>
      <div className="ops-cards">
        {nodes.map((n) => (
          <div className="ops-card" key={n.name}>
            <h3>
              <span className={`ops-dot ops-${n.ready ? "ok" : "ng"}`} /> 노드 <span className="mono">{n.name}</span>
            </h3>
            <Meter
              label={`CPU ${n.cpu_cores}코어`}
              used={n.cpu_used_m}
              total={n.cpu_cores * 1000}
              text={`${((n.cpu_used_m / (n.cpu_cores * 1000)) * 100).toFixed(0)}%`}
            />
            <Meter
              label="메모리 (WSL 기준, 캐시 일부 포함)"
              used={n.memory_used_mib}
              total={n.memory_total_mib}
              text={`${gib(n.memory_used_mib)} / ${gib(n.memory_total_mib)} GiB`}
            />
            {disk && (
              <Meter label="디스크" used={disk.used_gib} total={disk.total_gib} text={`${disk.used_gib.toFixed(0)} / ${disk.total_gib.toFixed(0)} GiB`} />
            )}
            <p className="hint ops-spec">{n.os} · {n.arch} · k8s {n.kubelet} · {n.runtime}</p>
          </div>
        ))}
        <div className="ops-card">
          <h3>GPU</h3>
          {gpu.gpus.length === 0 && <p className="hint">읽을 수 없습니다. {gpu.error}</p>}
          {gpu.gpus.map((g) => (
            <div key={g.name}>
              <p className="ops-gpu-name">{g.name}</p>
              <Meter label="사용률" used={g.utilization_pct} total={100} text={`${g.utilization_pct}%`} />
              <Meter label="GPU 메모리" used={g.memory_used_mib} total={g.memory_total_mib} text={`${gib(g.memory_used_mib)} / ${gib(g.memory_total_mib)} GiB`} />
              <p className="hint ops-spec">
                {g.temperature_c ?? "-"}°C · {g.power_w ?? "-"} W · 드라이버 {g.driver}
              </p>
            </div>
          ))}
        </div>
        <div className="ops-card">
          <h3>
            <span className={`ops-dot ops-${ollama.available ? "ok" : "ng"}`} /> LLM (Ollama)
          </h3>
          {!ollama.available && <p className="hint">연결할 수 없습니다.</p>}
          {ollama.available && <p className="hint">버전 {ollama.version} · 클러스터 밖 WSL에서 실행</p>}
          {ollama.available && ollama.models.length === 0 && <p className="hint">지금 올라간 모델이 없습니다.</p>}
          {ollama.models.map((m) => (
            <p className="ops-model" key={m.name}>
              <span className="mono">{m.name}</span> <span className="muted small">GPU {gib(m.vram_mib)} GiB</span>
            </p>
          ))}
        </div>
      </div>
    </section>
  );
}

function ServicesPanel({ overview, error, onKill, onLogs }) {
  return (
    <section className="panel">
      <h2>서비스</h2>
      {!overview && <p className="hint">{error ?? "불러오는 중…"}</p>}
      {overview && (
        <div className="table-wrap">
          <table className="alarm-table">
            <thead>
              <tr>
                <th>서비스</th>
                <th>파드</th>
                <th>상태</th>
                <th>재시작</th>
                <th>실행 시간</th>
                <th>CPU</th>
                <th>메모리</th>
                <th>버전</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {overview.services.flatMap((s) =>
                (s.pods.length ? s.pods : [null]).map((p, i) => (
                  <tr key={p?.name ?? s.name}>
                    <td>{i === 0 ? SERVICE_LABEL[s.name] ?? s.name : ""}</td>
                    {p ? (
                      <>
                        <td className="mono small">
                          <button className="ops-link" onClick={() => onLogs(p.name)} title="로그 보기">
                            {p.name}
                          </button>
                        </td>
                        <td>
                          <span className={`ops-dot ops-${statusTone(p.status, p.ready, p.containers)}`} /> {p.status}
                        </td>
                        <td className={p.restarts > 0 ? "ops-warn-text" : ""}>{p.restarts}</td>
                        <td>{age(p.age_s)}</td>
                        <td className="mono">{p.cpu_m === null ? "-" : `${p.cpu_m.toFixed(0)}m`}</td>
                        <td className="mono">
                          {p.memory_mib === null ? "-" : `${p.memory_mib.toFixed(0)}`}
                          {p.memory_limit_mib ? ` / ${p.memory_limit_mib.toFixed(0)} MiB` : " MiB"}
                        </td>
                      </>
                    ) : (
                      <td colSpan={6} className="ops-warn-text">파드 없음</td>
                    )}
                    <td className="mono small">{i === 0 ? s.version : ""}</td>
                    <td>
                      {i === 0 && s.killable && (
                        <button className="btn ops-kill" onClick={() => onKill(s.name)}>
                          파드 죽이기
                        </button>
                      )}
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function KillDialog({ service, onCancel, onConfirm, busy, error }) {
  const [token, setToken] = useState("");
  return (
    <div className="dialog-backdrop">
      <form
        className="dialog"
        onSubmit={(e) => {
          e.preventDefault();
          onConfirm(token);
        }}
      >
        <h2>{SERVICE_LABEL[service]} 파드를 죽일까요?</h2>
        <p className="hint">
          k8s가 새 파드를 자동으로 띄우는 과정을 보여 줍니다. 파드가 하나뿐이라 복구될 때까지 이 서비스는 잠깐 끊깁니다.
        </p>
        <label className="field">
          운영 토큰
          <input type="password" value={token} autoFocus autoComplete="off" onChange={(e) => setToken(e.target.value)} />
        </label>
        {error && <p className="hint analysis-error">{error}</p>}
        <div className="dialog-actions">
          <button type="button" className="btn-text" onClick={onCancel}>
            취소
          </button>
          <button className="btn" disabled={!token || busy}>
            {busy ? "요청 중…" : "죽이기"}
          </button>
        </div>
      </form>
    </div>
  );
}

/** Follows one service after a kill: every change in its pods becomes a line, until it is healthy again. */
function useRecovery() {
  const [recovery, setRecovery] = useState(null);
  const seen = useRef("");

  useEffect(() => {
    if (!recovery || recovery.done) return undefined;
    const started = recovery.startedAt;
    const timer = window.setInterval(async () => {
      let overview;
      try {
        overview = await fetchJson(`${API}/overview`);
      } catch {
        return; // keep following; the next tick tries again
      }
      const service = overview.services.find((s) => s.name === recovery.service);
      if (!service) return;
      const now = service.pods.map((p) => `${p.name.split("-").slice(-1)[0]} ${p.status} ${p.ready}/${p.containers}`).join(" · ") || "파드 없음";
      const healthy = service.ready >= service.desired && service.pods.length === service.desired
        && service.pods.every((p) => p.status === "Running" && p.ready === p.containers && p.name !== recovery.killed);
      setRecovery((r) => {
        if (!r) return r;
        const steps = now === seen.current ? r.steps : [...r.steps, { at: clock(), text: now }];
        seen.current = now;
        return healthy ? { ...r, steps, done: true, seconds: (Date.now() - started) / 1000 } : { ...r, steps };
      });
    }, WATCH_MS);
    return () => window.clearInterval(timer);
  }, [recovery]);

  const start = (service, killed) => {
    seen.current = "";
    setRecovery({ service, killed, startedAt: Date.now(), done: false, steps: [{ at: clock(), text: `${killed} 삭제 요청` }] });
  };
  return { recovery, start };
}

function RecoveryPanel({ recovery }) {
  if (!recovery) return null;
  return (
    <section className="panel">
      <h2>
        복구 과정 · {SERVICE_LABEL[recovery.service]}
        {recovery.done ? ` · ${recovery.seconds.toFixed(1)}초 만에 복구` : " · 진행 중"}
      </h2>
      <ol className="ops-steps" aria-live="polite">
        {recovery.steps.map((s, i) => (
          <li key={`${s.at}${i}`}>
            <span className="mono muted">{s.at}</span> <span className="mono">{s.text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function LogsPanel({ pod, onClose }) {
  const [text, setText] = useState("불러오는 중…");
  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/logs/${pod}?tail=200`)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`응답 ${r.status}`))))
      .then((t) => {
        if (!cancelled) setText(t || "(로그 없음)");
      })
      .catch((e) => {
        if (!cancelled) setText(`로그를 읽을 수 없습니다: ${e.message}`);
      });
    return () => {
      cancelled = true;
    };
  }, [pod]);
  return (
    <section className="panel">
      <div className="ops-panel-head">
        <h2>
          로그 · <span className="mono">{pod}</span> (최근 200줄)
        </h2>
        <button className="btn-text" onClick={onClose}>
          닫기
        </button>
      </div>
      <pre className="ops-logs">{text}</pre>
    </section>
  );
}

function EventsPanel({ events }) {
  if (!events) return null;
  return (
    <section className="panel">
      <h2>최근 이벤트</h2>
      {events.length === 0 && <p className="hint">최근 이벤트가 없습니다. k8s는 이벤트를 1시간 정도만 보관합니다.</p>}
      {events.length > 0 && (
        <div className="table-wrap ops-events">
          <table className="alarm-table">
            <thead>
              <tr>
                <th>시각</th>
                <th>대상</th>
                <th>사유</th>
                <th>내용</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={`${e.at}${e.object}${i}`} className={e.type === "Warning" ? "active" : ""}>
                  <td className="mono">{e.at ? new Date(e.at).toTimeString().slice(0, 8) : "-"}</td>
                  <td className="mono small">{e.object}</td>
                  <td>{e.reason}</td>
                  <td className="detail">{e.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function OpsPage() {
  const { data: overview, error: overviewError } = usePolling(`${API}/overview`, OVERVIEW_MS);
  const { data: infra, error: infraError } = usePolling(`${API}/infra`, INFRA_MS);
  const { recovery, start } = useRecovery();
  const [killing, setKilling] = useState(null);
  const [busy, setBusy] = useState(false);
  const [killError, setKillError] = useState(null);
  const [logsPod, setLogsPod] = useState(null);

  const kill = async (token) => {
    setBusy(true);
    setKillError(null);
    try {
      const res = await fetch(`${API}/services/${killing}/kill`, { method: "POST", headers: { "X-Ops-Token": token } });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail ?? `응답 ${res.status}`);
      start(killing, body.killed);
      setKilling(null);
    } catch (e) {
      setKillError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="console">
      {overviewError && overview && <p className="hint analysis-error">최신 상태를 가져오지 못했습니다: {overviewError}</p>}
      <InfraPanel infra={infra} error={infraError} />
      <ServicesPanel
        overview={overview}
        error={overviewError}
        onKill={(service) => {
          setKillError(null);
          setKilling(service);
        }}
        onLogs={setLogsPod}
      />
      <RecoveryPanel recovery={recovery} />
      {logsPod && <LogsPanel pod={logsPod} onClose={() => setLogsPod(null)} />}
      <EventsPanel events={overview?.events} />
      {killing && (
        <KillDialog service={killing} busy={busy} error={killError} onCancel={() => setKilling(null)} onConfirm={kill} />
      )}
    </main>
  );
}
