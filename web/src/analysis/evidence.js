import { localized, tr } from "../prefs";
import { FAULT_LABEL } from "../labels";

// Shared by the analysis tab and the real-time alert bar, so both describe the same evidence the same way.

export const faultName = (name) => FAULT_LABEL[name] ?? { unknown: tr("판단 불가"), no_fault: tr("고장 아님") }[name] ?? name;

// The values the guard watches (FEATURES in analysis/app/anomaly.py).
export const FEATURE = localized({
  bead_width_mm: { label: "비드 폭", unit: "mm", digits: 3 },
  bead_offset_mm: { label: "비드 오프셋", unit: "mm", digits: 3 },
  disp_pressure_kpa: { label: "토출 압력", unit: "kPa", digits: 1 },
  vacuum_kpa: { label: "진공", unit: "kPa", digits: 1 },
  ng_10min: { label: "10분 불량 수" },
});

export const time = (t) => t.slice(11, 19);
const num = (v, digits = 1) => Number(v).toFixed(digits);

/** One line of evidence for the guard, from the evidence dict in anomaly.py. */
export function anomalyText(e) {
  if (e.feature === "ng_10min") {
    return tr("최근 10분 불량 {a}개 (평소 최대 {b}개), {c}", { a: e.count_10min, b: e.normal_max, c: e.recipe });
  }
  const { unit, digits } = FEATURE[e.feature];
  const usual = `${num(e.normal_mean, digits)} ± ${num(e.normal_std, digits)} ${unit}`;
  return tr("{a} {b} (평소 {c}, 표준편차의 {d}배 벗어남), {e}", { a: num(e.value, digits), b: unit, c: usual, d: num(Math.abs(e.z)), e: e.recipe });
}

/** One line of evidence per rule, from the evidence dict each rule leaves in rules.py. */
export function evidenceText(type, e) {
  if (type === "anomaly") {
    return `${FEATURE[e.feature]?.label ?? e.feature}: ${anomalyText(e)}`;
  }
  if (type === "air_supply_drop") {
    return tr("압력 {a} kPa, 진공 {b} kPa 상태가 토출 중 {c}번 연속", { a: num(e.pressure_kpa), b: num(e.vacuum_kpa), c: e.consecutive });
  }
  if (type === "vacuum_leak") {
    return tr("진공 중앙값 {a} kPa로 약해짐 (압력 중앙값 {b} kPa는 정상)", { a: num(e.vacuum_median_kpa), b: num(e.pressure_median_kpa) });
  }
  if (type === "nozzle_clog") {
    return tr("비드 폭 중앙값 {a} → {b} mm (30분 사이), {c}", { a: num(e.width_median_30min_ago_mm, 3), b: num(e.width_median_mm, 3), c: e.recipe });
  }
  if (type === "recipe_pressure_error" || type === "recipe_retract_error") {
    return tr("{a}가 {b}를 {c} → {d}로 변경 (표준 {e}, {f}%), {g}", { a: e.by, b: e.param, c: e.old, d: e.new, e: e.standard, f: e.deviation_pct, g: e.recipe });
  }
  if (type === "air_bubble") {
    return tr("BEAD_VOID 불량이 {a}분 안에 {b}개 (첫 VOID {c}), {d}", { a: e.window_min, b: e.void_count, c: time(e.first_void_at), d: e.recipe });
  }
  if (type === "needle_offset") {
    return tr("최근 {a}개 제품의 비드 오프셋 중앙값 {b} mm (정상 약 0.010, 불량 기준 0.10), {c}", { a: e.window, b: num(e.offset_median_mm, 3), c: e.recipe });
  }
  if (type === "needle_tip_buildup") {
    return tr("STRINGING 불량이 {a}분 안에 {b}개 (첫 STRINGING {c}, retract 설정은 정상), {d}", { a: e.window_min, b: e.stringing_count, c: time(e.first_stringing_at), d: e.recipe });
  }
  return Object.entries(e).map(([k, v]) => `${k}=${v}`).join(", ");
}
