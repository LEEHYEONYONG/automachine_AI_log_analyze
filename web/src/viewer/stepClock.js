import { useCallback, useLayoutEffect, useRef } from "react";

/**
 * State arrives every 0.1 s, but motion should look continuous. Between updates the
 * step progress is advanced locally at the simulation speed, then re-anchored to the
 * server value when the next update arrives.
 */
export function useStepClock(station, running, speed) {
  const anchor = useRef({ progress: 0, t: 0, rate: 0 });
  const rate = running && station.step_s > 0 ? speed / station.step_s : 0;
  // Runs before the next frame is drawn, so useFrame never sees a stale anchor.
  useLayoutEffect(() => {
    anchor.current = { progress: station.progress, t: performance.now(), rate };
  }, [station.step, station.progress, rate]);
  return useCallback(() => {
    const cur = anchor.current;
    return Math.min(1, cur.progress + ((performance.now() - cur.t) / 1000) * cur.rate);
  }, []);
}
