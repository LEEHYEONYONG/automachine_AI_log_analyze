import { useEffect, useState } from "react";

async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json().catch(() => null);
}

export const api = {
  command: (cmd) => post(`/api/machine/${cmd}`),
  estop: (pressed) => post("/api/safety/estop", { pressed }),
  door: (door, open) => post("/api/safety/door", { door, open }),
  login: (user, pin) => post("/api/login", { user, pin }),
  logout: () => post("/api/logout"),
  setOpMode: (mode) => post("/api/opmode", { mode }),
  initialize: (clearParts) => post("/api/initialize", { clear_parts: clearParts }),
  device: (device, on) => post("/api/manual/device", { device, on }),
  jog: (axis, mm) => post("/api/manual/axis", { axis, jog: mm }),
  preset: (axis, preset) => post("/api/manual/axis", { axis, preset }),
  homeAll: () => post("/api/manual/home_all"),
  maintenance: (action) => post("/api/maintenance", { action }),
  setAutoOperator: (auto) => post("/api/operator", { auto }),
  setSim: (opts) => post("/api/sim", opts),
  newRun: (scenario) => post("/api/runs", { scenario }),
  changeRecipe: (recipe) => post("/api/recipe", { recipe }),
  injectFault: (type, params, delayMin) =>
    post("/api/faults", { type, params, delay_min: delayMin }),
  saveSettings: (values) => post("/api/settings", { values }),
  standardSettings: (keys) => post("/api/settings/standard", { keys: keys ?? null }),
  setRunMode: (mode, dummyCount, noMotion) =>
    post("/api/runmode", { mode, dummy_count: dummyCount, no_motion: noMotion }),
  resetCounters: () => post("/api/counters/reset"),
};

/** Trend data for the last `minutes` of simulated time, refreshed every second.
 *  The previous data stays on screen while a refresh is in flight. */
export function useTrends(minutes) {
  const [trends, setTrends] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetch(`/api/trends?minutes=${minutes}`)
        .then((r) => r.json())
        .then((t) => {
          if (!cancelled) setTrends(t);
        })
        .catch(() => {});
    load();
    const timer = window.setInterval(load, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [minutes]);
  return trends;
}

/** Static lists (scenarios, fault types, actions) fetched once. */
export function useMeta() {
  const [meta, setMeta] = useState(null);
  useEffect(() => {
    fetch("/api/meta")
      .then((r) => r.json())
      .then(setMeta)
      .catch(() => setMeta(null));
  }, []);
  return meta;
}

/** Live machine state from the server's WebSocket, reconnecting if the server restarts. */
export function useMachineState() {
  const [state, setState] = useState(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let ws;
    let retry;
    let disposed = false;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => setConnected(true);
      ws.onmessage = (e) => setState(JSON.parse(e.data));
      ws.onclose = () => {
        setConnected(false);
        if (!disposed) retry = window.setTimeout(connect, 1000);
      };
    };
    connect();

    return () => {
      disposed = true;
      window.clearTimeout(retry);
      ws.close();
    };
  }, []);

  return { state, connected };
}
