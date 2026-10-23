import type { MachineMode, StationState } from "./types";

export const MODE_LABEL: Record<MachineMode, string> = {
  RUNNING: "운전 중",
  STOPPED: "정지",
  ALARM: "알람",
};

export const STATION_STATE_LABEL: Record<StationState, string> = {
  IDLE: "대기",
  BUSY: "작업 중",
  DONE: "배출 대기",
  ALARM: "알람",
};

export const STATION_LABEL: Record<string, string> = {
  LOADER: "투입",
  VISION: "비전 정렬",
  DISPENSER: "디스펜싱",
  INSPECTION: "도포 검사",
  UNLOADER: "배출",
};

export const ACTION_LABEL: Record<string, string> = {
  supply_magazine: "매거진 보충",
  swap_output_tray: "배출 트레이 교체",
  remove_part: "제품 제거",
  vision_check: "비전 점검",
  vacuum_check: "진공 점검",
  replace_pick_pad: "흡착 패드 교체",
  nozzle_clean: "노즐 청소",
  purge: "퍼지 (기포 제거)",
  needle_calibration: "니들 캘리브레이션",
  replace_syringe: "시린지 교체",
  air_check: "에어 공급 확인",
  call_engineer: "엔지니어 점검",
};

/** Labels for actions that only the simulated operator takes. */
export const OPERATOR_ONLY_ACTION_LABEL: Record<string, string> = {
  model_change: "모델 체인지",
  none: "조치 없이 리셋",
  "self: bubbles dispensed out": "저절로 해소 (기포 소진)",
  "self: plant air recovered": "저절로 해소 (에어 회복)",
};

export const OPERATOR_PHASE_LABEL: Record<string, string> = {
  idle: "대기",
  ack: "알람 확인 중",
  work: "조치 중",
  break: "휴식 중",
  changeover_wait: "모델 체인지 준비",
};

export const FAULT_LABEL: Record<string, string> = {
  nozzle_clog: "노즐 막힘",
  vacuum_leak: "흡착 패드 누설",
  temp_sensor_drift: "온도 센서 드리프트",
  air_bubble: "시린지 기포",
  needle_tip_buildup: "니들 끝 접착제 누적 (실 끊김)",
  needle_offset: "니들 높이/위치 틀어짐",
  air_supply_drop: "공장 에어 공급압 저하",
  recipe_pressure_error: "레시피 압력 오입력",
  recipe_retract_error: "레시피 dwell 오입력",
};

export const FAULT_PARAM_LABEL: Record<string, string> = {
  ramp_min: "최대치까지 걸리는 시간 (분)",
  min_open_ratio: "최소 노즐 개방률 (0~1)",
  max_leak_ratio: "최대 누설률 (0~1)",
  max_offset_c: "최대 센서 오차 (°C)",
  bubbles: "기포 개수",
  void_probability: "도포당 끊김 확률 (0~1)",
  max_buildup: "최대 누적량 (0~1)",
  dz_mm: "니들 높이 오차 (mm, +는 높음)",
  dxy_mm: "니들 위치 오차 (mm)",
  min_supply_kpa: "최저 공급압 (kPa)",
  hold_min: "저하 유지 시간 (분)",
  wrong_pressure_kpa: "잘못 입력된 압력 (kPa)",
  wrong_retract_delay_s: "잘못 입력된 dwell (초)",
};

export const FAULT_STATE_LABEL: Record<string, string> = {
  pending: "예약됨",
  active: "진행 중",
  resolved: "해결됨",
};

export const SCENARIO_LABEL: Record<string, string> = {
  normal: "정상 가동",
  nozzle_clog: "노즐 막힘",
  vacuum_leak: "흡착 패드 누설",
  temp_sensor_drift: "온도 센서 드리프트",
  air_bubble: "시린지 기포",
  stringing: "실 끊김",
  needle_offset: "니들 틀어짐",
  air_supply_drop: "에어 공급압 저하",
  recipe_error: "레시피 오입력",
  realistic_day: "현실적인 하루 (12시간 복합)",
};

/** Maintenance actions in the order they appear on the HMI. */
export const MAINTENANCE_ACTIONS = Object.keys(ACTION_LABEL);
