import { useEffect, useState } from "react";

// The real-time watch (analysis/app/watch.py) follows the simulator's current run. k8s only; not in Compose.
const WATCH_API = "/api/analysis/watch";
// Equipment alarms arrive over the WebSocket at once, so a slow poll could show an earlier AI alert after them.
const WATCH_MS = 1000;

/** The watch's state, polled. null until the first answer, and while the watch cannot be reached. */
export function useWatch() {
  const [data, setData] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetch(WATCH_API)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => !cancelled && setData(d))
        .catch(() => !cancelled && setData(null));
    load();
    const timer = window.setInterval(load, WATCH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);
  return data;
}
