import { createContext, useContext } from "react";
import { EN } from "./i18n/en";

/*
 * Display settings for this browser only (theme, text size, language ...). Machine settings live on the
 * server; these do not, because several people watch the same machine from their own devices.
 *
 * Translation: the Korean text is the key. t("자동 운전") gives the English entry when the language is
 * English and one exists, otherwise the Korean. {name} in the text is filled from vars.
 */

export const STORAGE_KEY = "automachine.prefs";
export const DEFAULT_PREFS = {
  lang: "ko",
  theme: "dark",          // dark | light | system
  textSize: "normal",     // small | normal | large
  alarmSound: false,
  trendMinutes: 60,
  aiBar: true,
  viewerEffects: true,
};
export const TEXT_ZOOM = { small: 0.9, normal: 1, large: 1.15 };

export function loadPrefs() {
  try {
    return { ...DEFAULT_PREFS, ...JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}") };
  } catch {
    return DEFAULT_PREFS;
  }
}

function fill(text, vars) {
  return vars ? text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : text;
}

export function translate(lang, text, vars) {
  if (text == null) return text;
  const s = String(text);
  return fill(lang === "en" ? EN[s] ?? s : s, vars);
}

export const PrefsContext = createContext({
  prefs: DEFAULT_PREFS,
  setPref: () => {},
  t: (s, v) => translate("ko", s, v),
});

export function usePrefs() {
  return useContext(PrefsContext);
}

/** Just the translate function, for components that only show text. */
export function useT() {
  return useContext(PrefsContext).t;
}
