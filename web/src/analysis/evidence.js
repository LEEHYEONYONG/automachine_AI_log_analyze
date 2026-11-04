import { FAULT_LABEL } from "../labels";

// Shared by the analysis tab and the real-time alert bar, so both describe the same evidence the same way.

export const faultName = (name) => FAULT_LABEL[name] ?? { unknown: "판단 불가", no_fault: "고장 아님" }[name] ?? name;

// The values the guard watches (FEATURES in analysis/app/anomaly.py).
export const FEATURE = {
  bead_width_mm: { label: "비드 폭", unit: "mm", digits: 3 },
  bead_offset_mm: { label: "비드 오프셋", unit: "mm", digits: 3 },
  disp_pressure_kpa: { label: "토출 압력", unit: "kPa", digits: 1 },
  vacuum_kpa: { label: "진공", unit: "kPa", digits: 1 },
  ng_10min: { label: "10분 불량 수" },
};

export const time = (t) => t.slice(11, 19);
const num = (v, digits = 1) => Number(v).toFixed(digits);

/** One line of evidence for the guard, from the evidence dict in anomaly.py. */
export function anomalyText(e) {
  if (e.feature === "ng_10min") {
    return `최근 10분 불량 ${e.count_10min}개 (평소 최대 ${e.normal_max}개), ${e.recipe}`;
  }
  const { unit, digits } = FEATURE[e.feature];
  const usual = `${num(e.normal_mean, digits)} ± ${num(e.normal_std, digits)} ${unit}`;
  return `${num(e.value, digits)} ${unit} (평소 ${usual}, 표준편차의 ${num(Math.abs(e.z))}배 벗어남), ${e.recipe}`;
}

/** One line of evidence per rule, from the evidence dict each rule leaves in rules.py. */
export function evidenceText(type, e) {
  if (type === "anomaly") {
    return `${FEATURE[e.feature]?.label ?? e.feature}: ${anomalyText(e)}`;
  }
  if (type === "air_supply_drop") {
    return `압력 ${num(e.pressure_kpa)} kPa, 진공 ${num(e.vacuum_kpa)} kPa 상태가 토출 중 ${e.consecutive}번 연속`;
  }
  if (type === "vacuum_leak") {
    return `진공 중앙값 ${num(e.vacuum_median_kpa)} kPa로 약해짐 (압력 중앙값 ${num(e.pressure_median_kpa)} kPa는 정상)`;
  }
  if (type === "nozzle_clog") {
    return `비드 폭 중앙값 ${num(e.width_median_30min_ago_mm, 3)} → ${num(e.width_median_mm, 3)} mm (30분 사이), ${e.recipe}`;
  }
  if (type === "recipe_pressure_error" || type === "recipe_retract_error") {
    return `${e.by}가 ${e.param}를 ${e.old} → ${e.new}로 변경 (표준 ${e.standard}, ${e.deviation_pct}%), ${e.recipe}`;
  }
  if (type === "air_bubble") {
    return `BEAD_VOID 불량이 ${e.window_min}분 안에 ${e.void_count}개 (첫 VOID ${time(e.first_void_at)}), ${e.recipe}`;
  }
  if (type === "needle_offset") {
    return `최근 ${e.window}개 제품의 비드 오프셋 중앙값 ${num(e.offset_median_mm, 3)} mm (정상 약 0.010, 불량 기준 0.10), ${e.recipe}`;
  }
  if (type === "needle_tip_buildup") {
    return `STRINGING 불량이 ${e.window_min}분 안에 ${e.stringing_count}개 (첫 STRINGING ${time(e.first_stringing_at)}, retract 설정은 정상), ${e.recipe}`;
  }
  return Object.entries(e).map(([k, v]) => `${k}=${v}`).join(", ");
}
