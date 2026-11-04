import { useEffect, useRef } from "react";

let context = null;

/** A short two-tone beep like a panel buzzer. Browsers only allow sound after the page has been clicked once. */
export function beep(times = 1) {
  try {
    context ??= new (window.AudioContext || window.webkitAudioContext)();
    context.resume?.();
    for (let i = 0; i < times; i += 1) {
      const start = context.currentTime + i * 0.45;
      const osc = context.createOscillator();
      const gain = context.createGain();
      osc.type = "square";
      osc.frequency.setValueAtTime(880, start);
      osc.frequency.setValueAtTime(660, start + 0.15);
      gain.gain.setValueAtTime(0.08, start);
      gain.gain.setValueAtTime(0, start + 0.3);
      osc.connect(gain).connect(context.destination);
      osc.start(start);
      osc.stop(start + 0.32);
    }
  } catch {
    // no audio device or the browser refused: the alarm is still shown on screen
  }
}

/** Beep when a new alarm is raised, if this browser has alarm sound turned on. */
export function useAlarmSound(alarm, enabled) {
  const last = useRef(alarm?.set_at ?? null);
  useEffect(() => {
    const at = alarm?.set_at ?? null;
    if (at && at !== last.current && enabled) beep(3);
    last.current = at;
  }, [alarm?.set_at, enabled]);
}
