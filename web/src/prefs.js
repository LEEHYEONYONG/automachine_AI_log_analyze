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

// Messages the server builds with values in them (simulator/settings.py, server/session.py ...).
const EN_PATTERNS = [
  [/^(.+): (.+)~(.+?) ?(\S*) 범위여야 합니다 \(입력 (.+)\)$/, (m) => `${en(m[1])}: must be ${m[2]} to ${m[3]} ${en(m[4])} (entered ${m[5]})`],
  [/^(.+): 숫자를 넣어 주세요$/, (m) => `${en(m[1])}: enter a number`],
  [/^권한이 없습니다: (\w+) 이상 필요 \(현재 (\w+)\)$/, (m) => `Not permitted: needs ${m[1]} or higher (now ${m[2]})`],
  [/^권한이 없습니다: (.+)은\(는\) (\w+) 이상 필요 \(현재 (\w+)\)$/, (m) => `Not permitted: ${en(m[1])} needs ${m[2]} or higher (now ${m[3]})`],
  [/^더미 수량은 1~(\d+)개여야 합니다$/, (m) => `Dummy parts must be 1 to ${m[1]}`],
  [/^알 수 없는 설정: (.+)$/, (m) => `Unknown setting: ${m[1]}`],
  [/^(투입|비전|디스펜서|검사|배출) (제품 감지|스토퍼 상승 센서|스토퍼 하강 솔레노이드|컨베이어 모터)$/,
    (m) => `${en(m[1])} ${({ "제품 감지": "part sensor", "스토퍼 상승 센서": "stopper up sensor", "스토퍼 하강 솔레노이드": "stopper down solenoid", "컨베이어 모터": "conveyor motor" })[m[2]]}`],
  [/^안전 조건 미충족: (.+)$/, (m) => `Safety conditions not met: ${m[1].split(", ").map(en).join(", ")}`],
];

function en(s) {
  const exact = EN[s];
  if (exact !== undefined) return exact;
  if (s.includes("; ")) return s.split("; ").map(en).join("; ");
  for (const [re, make] of EN_PATTERNS) {
    const m = re.exec(s);
    if (m) return make(m);
  }
  return s;
}

export function translate(lang, text, vars) {
  if (text == null) return text;
  const s = String(text);
  return fill(lang === "en" ? en(s) : s, vars);
}

// The language now on screen, for label tables read outside of components. PrefsProvider sets it
// while rendering, and a language change re-renders the whole app, so tables read during render agree.
let currentLang = "ko";
export function setCurrentLang(lang) {
  currentLang = lang;
}

/** Translate outside of a hook (inside a component's render, the result matches t()). */
export function tr(text, vars) {
  return translate(currentLang, text, vars);
}

/** A label table whose strings come out in the current language (nested objects and arrays too).
 *  Lets the many places that read e.g. STEP_LABEL[step] stay as they are. */
export function localized(table) {
  return new Proxy(table, {
    get(target, key, receiver) {
      const value = Reflect.get(target, key, receiver);
      if (typeof value === "string") return translate(currentLang, value);
      if (value && typeof value === "object") return localized(value);
      return value;
    },
  });
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
