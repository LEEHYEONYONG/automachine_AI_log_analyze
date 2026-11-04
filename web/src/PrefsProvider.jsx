import { useCallback, useEffect, useMemo, useState } from "react";
import { loadPrefs, PrefsContext, STORAGE_KEY, TEXT_ZOOM, translate } from "./prefs";

function systemDark() {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true;
}

/** Holds this browser's display settings and applies theme, text size and language to the page. */
export function PrefsProvider({ children }) {
  const [prefs, setPrefs] = useState(loadPrefs);
  const [dark, setDark] = useState(systemDark);

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return undefined;
    const onChange = () => setDark(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = prefs.theme === "system" ? (dark ? "dark" : "light") : prefs.theme;
    root.style.setProperty("--ui-zoom", String(TEXT_ZOOM[prefs.textSize] ?? 1));
    root.lang = prefs.lang;
  }, [prefs.theme, prefs.textSize, prefs.lang, dark]);

  const setPref = useCallback((key, value) => {
    setPrefs((p) => {
      const next = { ...p, [key]: value };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // private window or blocked storage: the setting still applies until the page is closed
      }
      return next;
    });
  }, []);

  const t = useCallback((text, vars) => translate(prefs.lang, text, vars), [prefs.lang]);
  const value = useMemo(() => ({ prefs, setPref, t }), [prefs, setPref, t]);
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}
