import { useEffect, useRef, useState } from "react";

// The operations API only exists on k8s; under Compose this path reaches the simulator, which answers 404.
const API = "/api/ops";
const OVERVIEW_MS = 2000;
const INFRA_MS = 3000;
const STORAGE_MS = 30000; // sizes change slowly, and adding up the logs reads every file's size
const DEPLOYMENTS_MS = 3000;
const AUTOSCALE_MS = 2000;
const TRAFFIC_MS = 15000; // the API reads Traefik this often, so asking more often shows nothing new
const BACKUP_STALE_S = 36 * 3600; // a daily backup, plus room for the PC having been off
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

const usageTone = (pct) => (pct >= 90 ? "ng" : pct >= 70 ? "warn" : "ok");

/** Why a container last stopped, from what k8s recorded. Exit codes above 128 mean a signal ended it. */
function stopReason({ reason, exit_code: code }) {
  if (reason === "OOMKilled") return "메모리 한도 초과";
  if (reason === "Completed") return "정상 종료";
  if (reason === "Unknown") return "PC 또는 k3s 재시작으로 추정";
  if (code === 137) return "강제 종료 (137)";
  if (code === 143) return "종료 요청 (143)";
  return `${reason ?? "오류"} (코드 ${code ?? "?"})`;
}

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
  const tone = usageTone(pct);
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

const size = (mib) => (mib >= 1024 ? `${gib(mib)} GiB` : `${mib.toFixed(0)} MiB`);

function backupHealth({ files, last_job: lastJob, error }) {
  if (error) return { tone: "ng", text: error };
  if (lastJob?.state === "실패") return { tone: "ng", text: `마지막 백업 실패 (${age(lastJob.age_s)} 전)` };
  if (files.length === 0) return { tone: "ng", text: "백업 없음" };
  if (files[0].age_s > BACKUP_STALE_S) return { tone: "warn", text: `마지막 성공 ${age(files[0].age_s)} 전, 오래됨` };
  return { tone: "ok", text: `마지막 성공 ${age(files[0].age_s)} 전` };
}

function StoragePanel({ storage, error }) {
  if (!storage) return <section className="panel"><h2>저장 공간과 백업</h2><p className="hint">{error ?? "불러오는 중…"}</p></section>;
  const { db, logs, backup } = storage;
  const health = backupHealth(backup);
  return (
    <section className="panel">
      <h2>저장 공간과 백업</h2>
      <div className="ops-cards">
        <div className="ops-card">
          <h3>
            <span className={`ops-dot ops-${db.available ? "ok" : "ng"}`} /> 데이터베이스
          </h3>
          {!db.available && <p className="hint">읽을 수 없습니다. {db.error}</p>}
          {db.available && (
            <>
              <Meter label="크기 / 요청한 볼륨" used={db.size_mib} total={db.capacity_mib} text={`${size(db.size_mib)} / ${size(db.capacity_mib ?? 0)}`} />
              <Meter label="연결 수" used={db.connections} total={db.max_connections} text={`${db.connections} / ${db.max_connections}`} />
              <ul className="ops-list">
                {db.tables.map((t) => (
                  <li key={t.name}>
                    <span className="mono">{t.name}</span>
                    <span className="mono">{size(t.size_mib)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
        <div className="ops-card">
          <h3>시뮬레이터 로그</h3>
          {!logs.available && <p className="hint">읽을 수 없습니다. {logs.error}</p>}
          {logs.available && (
            <p className="ops-gpu-name">
              <span className="mono">{size(logs.size_mib)}</span> · 런 {logs.runs}개
            </p>
          )}
          <p className="hint ops-spec">시뮬레이터를 재시작할 때마다 새 런이 쌓입니다. 자동으로 지우지 않습니다.</p>
        </div>
        <div className="ops-card">
          <h3>
            <span className={`ops-dot ops-${health.tone}`} /> DB 백업
          </h3>
          <p className="ops-gpu-name">{health.text}</p>
          {backup.schedule && (
            <p className="hint ops-spec">
              일정 <span className="mono">{backup.schedule}</span> ({backup.time_zone})
              {backup.last_job && ` · 최근 실행 ${backup.last_job.state}, ${age(backup.last_job.age_s)} 전`}
            </p>
          )}
          <ul className="ops-list">
            {backup.files.map((f) => (
              <li key={f.name}>
                <span className="mono">{f.name}</span>
                <span className="mono">{size(f.size_mib)}</span>
              </li>
            ))}
          </ul>
          <p className="hint ops-spec">이 PC에만 저장됩니다. 디스크 고장에 대비하려면 다른 곳에도 복사하세요.</p>
        </div>
      </div>
    </section>
  );
}

const ROLLOUT_TONE = { 완료: "ok", "진행 중": "warn", 대기: "warn", 멈춤: "ng" };

function VersionTag({ version }) {
  return (
    <>
      <span className="mono small">{version}</span>
      {version.includes("-dirty-") && <span className="ops-dirty">커밋 전 코드</span>}
    </>
  );
}

function DeploymentsPanel({ data, error }) {
  return (
    <section className="panel">
      <h2>배포 현황</h2>
      {!data && <p className="hint">{error ?? "불러오는 중…"}</p>}
      {data && (
        <div className="table-wrap">
          <table className="alarm-table">
            <thead>
              <tr>
                <th>서비스</th>
                <th>배포 상태</th>
                <th>새 버전 준비</th>
                <th>마지막 변경</th>
                <th>현재 버전과 이력</th>
              </tr>
            </thead>
            <tbody>
              {data.deployments.map((d) => (
                <tr key={d.name}>
                  <td>{SERVICE_LABEL[d.name] ?? d.name}</td>
                  <td title={d.message ?? undefined}>
                    <span className={`ops-dot ops-${ROLLOUT_TONE[d.state] ?? "warn"}`} /> {d.state}
                  </td>
                  <td className="mono">
                    {d.new_ready} / {d.desired}
                  </td>
                  <td>{d.last_change_s === null ? "-" : `${age(d.last_change_s)} 전`}</td>
                  <td>
                    <VersionTag version={d.version} />
                    {d.history.length > 1 && (
                      <details className="ops-history">
                        <summary>이력 {d.history.length}개</summary>
                        <ul className="ops-list">
                          {d.history.map((h) => (
                            <li key={h.revision}>
                              <span>
                                <span className="mono">#{h.revision}</span> <VersionTag version={h.version} />
                                {h.current && <strong> 현재</strong>}
                              </span>
                              <span>{age(h.created_s)} 전</span>
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function TrafficPanel({ data, error }) {
  const title = <h2>서비스 요청</h2>;
  if (!data) return <section className="panel">{title}<p className="hint">{error ?? "불러오는 중…"}</p></section>;
  const longMinutes = Math.max(1, Math.round(data.long_window_s / 60));
  return (
    <section className="panel">
      {title}
      {!data.available && <p className="hint analysis-error">Traefik 지표를 읽지 못했습니다. {data.error}</p>}
      {data.services.length === 0 && data.available && <p className="hint">측정 중입니다. 15초쯤 걸립니다.</p>}
      {data.services.length > 0 && (
        <div className="table-wrap">
          <table className="alarm-table">
            <thead>
              <tr>
                <th>서비스</th>
                <th>초당 요청</th>
                <th>서버 오류 (5xx)</th>
                <th>요청 오류 (4xx)</th>
                <th>응답 시간 (95%)</th>
                <th>5xx (최근 {longMinutes}분)</th>
              </tr>
            </thead>
            <tbody>
              {data.services.map((s) => (
                <tr key={s.name}>
                  <td>{s.name === "_all" ? <strong>전체 (입구)</strong> : SERVICE_LABEL[s.name] ?? s.name}</td>
                  <td className="mono">{s.per_second.toFixed(1)}</td>
                  <td className={`mono ${s.server_errors > 0 ? "ops-ng-text" : ""}`}>
                    {s.server_errors}
                    {s.requests > 0 && ` (${((s.server_errors / s.requests) * 100).toFixed(1)}%)`}
                  </td>
                  <td className="mono">{s.client_errors}</td>
                  <td className="mono">{s.p95_over ? "5초 초과" : s.p95_le === null ? "-" : `${s.p95_le}초 이내`}</td>
                  <td className={`mono ${s.server_errors_long > 0 ? "ops-ng-text" : ""}`}>{s.server_errors_long}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="hint ops-spec">
        최근 {data.window_s}초 기준입니다. Traefik을 거친 요청만 세므로 파드끼리의 요청과 부하 시험은 빠지고, 운영 API에는 이 화면의 자동 새로고침이 포함됩니다. 웹소켓은 제외합니다.
      </p>
      <p className="hint ops-spec">
        응답할 파드가 하나도 없을 때의 503은 서비스별 줄에 없고 "전체"에만 잡힙니다. "전체"에는 같은 입구를 쓰는 다른 프로젝트의 요청도 포함됩니다.
      </p>
    </section>
  );
}

function LoadDialog({ duration, onCancel, onConfirm, busy, error }) {
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
        <h2>부하 시험을 시작할까요?</h2>
        <p className="hint">AI 분석 파드에 {duration}초 동안 요청을 보냅니다. CPU가 오르면 파드가 늘고, 끝나면 줄어드는 과정을 볼 수 있습니다.</p>
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
            {busy ? "요청 중…" : "시작"}
          </button>
        </div>
      </form>
    </div>
  );
}

function AutoscalePanel({ data, error, stopError, onStart, onStop }) {
  if (!data) return <section className="panel"><h2>자동 확장 (HPA)</h2><p className="hint">{error ?? "불러오는 중…"}</p></section>;
  const { hpa, load, rescales } = data;
  return (
    <section className="panel">
      <h2>자동 확장 (HPA)</h2>
      <div className="ops-cards">
        <div className="ops-card">
          <h3>
            <span className={`ops-dot ops-${hpa.active ? "ok" : "warn"}`} /> {SERVICE_LABEL[hpa.name] ?? hpa.name}
          </h3>
          <Meter label={`파드 수 (최소 ${hpa.min}, 최대 ${hpa.max})`} used={hpa.current} total={hpa.max} text={`${hpa.current}개${hpa.desired !== hpa.current ? ` → ${hpa.desired}개` : ""}`} />
          <Meter label="CPU (요청한 양 대비, 파드 평균)" used={hpa.cpu_pct} total={100} text={`${hpa.cpu_pct}% / 목표 ${hpa.target_cpu_pct}%`} />
          {!hpa.active && <p className="hint ops-spec">CPU 측정값을 기다리는 중입니다.</p>}
        </div>
        <div className="ops-card">
          <h3>부하 시험</h3>
          {load.elapsed_s !== null && (
            <p className="ops-gpu-name">
              {load.running ? `진행 중 ${load.elapsed_s} / ${load.duration_s}초` : `끝남 (${load.elapsed_s}초)`} · 요청 {load.requests.toLocaleString()}개 · 실패 {load.errors.toLocaleString()}개
            </p>
          )}
          {load.running ? (
            <button className="btn" onClick={onStop}>멈추기</button>
          ) : (
            <button className="btn" onClick={onStart}>부하 시작</button>
          )}
          {stopError && load.running && <p className="hint analysis-error">{stopError}</p>}
          <p className="hint ops-spec">가벼운 상태 확인 요청을 반복합니다. 실제 분석 작업의 부하와는 다릅니다.</p>
        </div>
        <div className="ops-card">
          <h3>확장 기록</h3>
          {rescales.length === 0 && <p className="hint">최근 기록이 없습니다.</p>}
          <ul className="ops-list ops-rescales">
            {rescales.map((r) => (
              <li key={`${r.at}${r.message}`}>
                <span className="mono">{new Date(r.at).toTimeString().slice(0, 8)}</span>
                <span>{r.message}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

/** One table cell: the number, and how close it is to the pod's limit when it has one. */
function UsageCell({ label, used, limit, unit }) {
  if (used === null || used === undefined) return <td className="mono">-</td>;
  const pct = limit ? Math.min(100, (used / limit) * 100) : null;
  return (
    <td className="mono ops-usage">
      {used.toFixed(0)}
      {limit ? ` / ${limit.toFixed(0)}` : ""} {unit}
      {pct !== null && (
        <div className="ops-bar" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
          <div className={`ops-bar-fill ops-${usageTone(pct)}`} style={{ width: `${pct}%` }} />
        </div>
      )}
    </td>
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
                        <td>
                          <span className={p.restarts > 0 ? "ops-warn-text" : ""}>{p.restarts}</span>
                          {p.last_termination && (
                            <div className="ops-stop-reason">
                              {stopReason(p.last_termination)} · {age(p.last_termination.seconds_ago)} 전
                            </div>
                          )}
                        </td>
                        <td>{age(p.age_s)}</td>
                        <UsageCell label={`${p.name} CPU`} used={p.cpu_m} limit={p.cpu_limit_m} unit="m" />
                        <UsageCell label={`${p.name} 메모리`} used={p.memory_mib} limit={p.memory_limit_mib} unit="MiB" />
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
  const { data: storage, error: storageError } = usePolling(`${API}/storage`, STORAGE_MS);
  const { data: rollouts, error: rolloutsError } = usePolling(`${API}/deployments`, DEPLOYMENTS_MS);
  const { data: autoscale, error: autoscaleError } = usePolling(`${API}/autoscale`, AUTOSCALE_MS);
  const { data: traffic, error: trafficError } = usePolling(`${API}/traffic`, TRAFFIC_MS);
  const [loadDialog, setLoadDialog] = useState(false);
  const [loadBusy, setLoadBusy] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [stopError, setStopError] = useState(null);
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

  // Stopping twice does no harm, so one failed request is simply tried again.
  const stopLoad = async () => {
    setStopError(null);
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const res = await fetch(`${API}/loadtest/stop`, { method: "POST" }).catch(() => null);
      if (res?.ok) return;
    }
    setStopError("멈추지 못했습니다. 다시 눌러 보세요. 시간이 다 되면 저절로 끝납니다.");
  };

  const startLoad = async (token) => {
    setLoadBusy(true);
    setLoadError(null);
    try {
      const res = await fetch(`${API}/loadtest`, { method: "POST", headers: { "X-Ops-Token": token } });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail ?? `응답 ${res.status}`);
      setLoadDialog(false);
    } catch (e) {
      setLoadError(e.message);
    } finally {
      setLoadBusy(false);
    }
  };

  return (
    <main className="console">
      {overviewError && overview && <p className="hint analysis-error">최신 상태를 가져오지 못했습니다: {overviewError}</p>}
      <InfraPanel infra={infra} error={infraError} />
      <StoragePanel storage={storage} error={storageError} />
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
      <TrafficPanel data={traffic} error={trafficError} />
      <AutoscalePanel
        data={autoscale}
        error={autoscaleError}
        stopError={stopError}
        onStart={() => {
          setLoadError(null);
          setStopError(null);
          setLoadDialog(true);
        }}
        onStop={stopLoad}
      />
      <DeploymentsPanel data={rollouts} error={rolloutsError} />
      {logsPod && <LogsPanel pod={logsPod} onClose={() => setLogsPod(null)} />}
      <EventsPanel events={overview?.events} />
      {loadDialog && (
        <LoadDialog
          duration={autoscale?.load.duration_s}
          busy={loadBusy}
          error={loadError}
          onCancel={() => setLoadDialog(false)}
          onConfirm={startLoad}
        />
      )}
      {killing && (
        <KillDialog service={killing} busy={busy} error={killError} onCancel={() => setKilling(null)} onConfirm={kill} />
      )}
    </main>
  );
}
