import { useEffect, useState } from "react";
import type { MachineState, Meta, Trends } from "./types";

async function post(path: string, body?: unknown): Promise<void> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `${res.status} ${res.statusText}`);
  }
}

export const api = {
  command: (cmd: "start" | "stop" | "cycle_stop" | "reset") => post(`/api/machine/${cmd}`),
  setOpMode: (mode: "AUTO" | "MANUAL") => post("/api/opmode", { mode }),
  device: (device: string, on: boolean) => post("/api/manual/device", { device, on }),
  jog: (axis: string, mm: number) => post("/api/manual/axis", { axis, jog: mm }),
  preset: (axis: string, preset: string) => post("/api/manual/axis", { axis, preset }),
  homeAll: () => post("/api/manual/home_all"),
  maintenance: (action: string) => post("/api/maintenance", { action }),
  setAutoOperator: (auto: boolean) => post("/api/operator", { auto }),
  setSim: (opts: { speed?: number; paused?: boolean }) => post("/api/sim", opts),
  newRun: (scenario: string | null) => post("/api/runs", { scenario }),
  changeRecipe: (recipe: string) => post("/api/recipe", { recipe }),
  injectFault: (type: string, params: Record<string, number>, delayMin: number) =>
    post("/api/faults", { type, params, delay_min: delayMin }),
};

/** Trend data for the last `minutes` of simulated time, refreshed every second.
 *  The previous data stays on screen while a refresh is in flight. */
export function useTrends(minutes: number) {
  const [trends, setTrends] = useState<Trends | null>(null);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetch(`/api/trends?minutes=${minutes}`)
        .then((r) => r.json())
        .then((t: Trends) => {
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
  const [meta, setMeta] = useState<Meta | null>(null);
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
  const [state, setState] = useState<MachineState | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let ws: WebSocket;
    let retry: number | undefined;
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
