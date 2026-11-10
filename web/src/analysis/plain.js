import { localized, tr } from "../prefs";
import { ACTION_LABEL, FAULT_LABEL } from "../labels";
import { evidenceText, FEATURE, faultName, time } from "./evidence";

// Names shown on screen for the parts of the AI. The code keeps its own short names (rules, anomaly,
// classify, foreman); these say what each one does, in words someone new to the machine can follow.
export const TERM = localized({
  rule: "패턴 검사",
  anomaly: "이상 감지",
  classify: "유형 추정",
  decide: "원인 판정",
  report: "원인 분석 보고서",
});

export const TERM_HELP = localized({
  rule: "알려진 고장이 남기는 흔적(예: 압력이 낮은 채로 진공도 약해짐)과 일치하는지 봅니다. 고장 이름까지 알려 줍니다.",
  anomaly: "정상 운전 때 배운 값의 범위를 벗어났는지 봅니다. 처음 보는 고장도 찾지만 고장 이름은 모릅니다.",
  classify: "이상 감지가 울린 순간의 값을 지난 고장 사례들과 비교해 가장 비슷한 고장을 고릅니다. 참고용입니다.",
  decide: "위 세 결과를 정해진 순서로 따져 최종 원인을 정합니다. AI(LLM)는 이 결정을 바꾸지 못합니다.",
  report: "AI(LLM)가 측정·알람·정비 기록을 직접 찾아보고, 원인 판정의 근거를 글로 풀어 줍니다.",
});

/** "20261103_1126_c5f9ad" → "11/03 11:26 시작 (c5f9ad)": when the machine was started, which is what people remember. */
export function runName(id) {
  const m = /^\d{4}(\d\d)(\d\d)_(\d\d)(\d\d)_(\w+)$/.exec(id ?? "");
  return m ? tr("{a}/{b} {c}:{d} 시작 ({e})", { a: m[1], b: m[2], c: m[3], d: m[4], e: m[5] }) : id;
}

// Why the code chose the cause (analysis/app/foreman.py decide). The server text also goes into the LLM
// prompt, so it stays as it is there and is only reworded here.
export function plainBasis(basis) {
  if (!basis) return "";
  let m = /^규칙 ([a-z_]+)$/.exec(basis);
  if (m) return tr("알려진 고장 패턴과 일치");
  m = /^규칙은 노즐 막힘이지만 청소 뒤 폭이 돌아오지 않음 \((.+) → (.+) mm\)$/.exec(basis);
  if (m) return tr("노즐 막힘 패턴이었지만 노즐 청소 뒤에도 비드 폭이 돌아오지 않음 ({a} → {b} mm)", { a: m[1], b: m[2] });
  if (basis === "규칙 경보 없음, 분류 모델 의견") return tr("알려진 패턴은 없고, 지난 사례 중 가장 비슷한 고장");
  if (basis === "규칙 경보가 없고 분류 모델도 확신하지 못함") return tr("알려진 패턴이 없고 지난 사례와도 뚜렷이 닮지 않음");
  return tr(basis);
}

// Code names that the LLM or the server sometimes write as they are.
const IDS = {
  ...Object.fromEntries(Object.keys(FAULT_LABEL).map((k) => [k, () => FAULT_LABEL[k]])),
  ...Object.fromEntries(Object.keys(ACTION_LABEL).map((k) => [k, () => ACTION_LABEL[k]])),
  vacuum_kpa: () => FEATURE.vacuum_kpa.label,
  fixture_vac_kpa: () => FEATURE.vacuum_kpa.label,
  disp_pressure_kpa: () => FEATURE.disp_pressure_kpa.label,
  bead_width_mm: () => FEATURE.bead_width_mm.label,
  bead_offset_mm: () => FEATURE.bead_offset_mm.label,
  ng_10min: () => FEATURE.ng_10min.label,
  disp_temp_c: () => tr("시린지 온도"),
  get_readings: () => tr("측정값"),
  get_defects: () => tr("불량 기록"),
  get_alarms: () => tr("알람 기록"),
  get_work_history: () => tr("정비·설정 기록"),
  search_manual: () => tr("조치 매뉴얼"),
};
const ID_RE = new RegExp(`\\b(${Object.keys(IDS).join("|")})\\b`, "g");

// Our own nicknames, as they may appear in text the LLM wrote from its prompt.
const WORDS = [
  [/경비원/g, () => TERM.anomaly],
  [/분류 모델/g, () => tr("유형 추정 모델")],
  [/판단 코드|코드 판단|분석 코드/g, () => TERM.decide],
  [/안내서/g, () => tr("조치 매뉴얼")],
];

/** Text from the server or the LLM, with code names and our nicknames replaced by plain words. */
export function plainText(text) {
  if (!text) return text;
  let s = String(text).replace(ID_RE, (id) => IDS[id]());
  for (const [re, word] of WORDS) s = s.replace(re, word);
  // "공장 에어 공급압 저하 (공장 에어 공급압 저하)" after the swap: keep one.
  return s.replace(/(\S[^()]*?) \(\1\)/g, "$1");
}

/** One plain paragraph for an incident or a live alert: what was seen, what it means, how early, what to do. */
export function summary(i) {
  const seen = i.evidence ? plainText(evidenceText(i.evidence.type, i.evidence.data)) : null;
  const unknown = i.cause === "unknown";
  const lines = [
    seen
      ? tr("{a}부터 {b}.", { a: time(i.started_at), b: seen })
      : tr("{a}부터 정상 범위를 벗어난 값이 나타났습니다.", { a: time(i.started_at) }),
    unknown
      ? tr("원인은 아직 특정하지 못했습니다. 기록을 직접 확인해 주세요.")
      : tr("→ 원인 판정: {a} ({b}).", { a: faultName(i.cause), b: plainBasis(i.basis) }),
  ];
  if (i.first_alarm) {
    lines.push(
      i.lead_min >= 0
        ? tr("관련 설비 알람 {a}보다 {b}분 먼저 알렸습니다.", { a: i.first_alarm.code, b: Math.round(i.lead_min) })
        : tr("관련 설비 알람 {a}가 {b}분 먼저 울렸습니다.", { a: i.first_alarm.code, b: Math.round(-i.lead_min) }),
    );
  }
  // All the steps: the first one alone can mislead ("do not replace parts" for an air supply drop).
  return { text: lines.join(" "), todo: i.actions?.steps ? plainText(i.actions.steps) : null };
}

/** What each part of the AI said about this incident, as checkmarks. */
export function checks(i) {
  return [
    {
      key: "rule",
      hit: i.rule_names.length > 0,
      text: i.rule_names.length
        ? tr("알려진 고장 패턴과 일치: {a}", { a: i.rule_names.map(faultName).join(", ") })
        : tr("알려진 고장 패턴 없음"),
    },
    {
      key: "anomaly",
      hit: i.guard_values.length > 0,
      text: i.guard_values.length
        ? tr("정상 범위 벗어남: {a}", { a: i.guard_values.map((v) => FEATURE[v]?.label ?? v).join(", ") })
        : tr("정상 범위 안"),
    },
    {
      key: "classify",
      hit: !!i.tree_guess && i.tree_guess !== "unknown",
      text: i.tree_guess && i.tree_guess !== "unknown" ? tr("지난 사례와 비슷: {a}", { a: faultName(i.tree_guess) }) : tr("비슷한 지난 사례 없음"),
    },
  ];
}
