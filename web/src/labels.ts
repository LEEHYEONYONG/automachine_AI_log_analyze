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
  replace_syringe: "시린지 교체",
  call_engineer: "엔지니어 점검",
};

export const FAULT_LABEL: Record<string, string> = {
  nozzle_clog: "노즐 막힘",
  vacuum_leak: "흡착 패드 누설",
  temp_sensor_drift: "온도 센서 드리프트",
};

export const FAULT_PARAM_LABEL: Record<string, string> = {
  ramp_min: "최대치까지 걸리는 시간 (분)",
  min_open_ratio: "최소 노즐 개방률 (0~1)",
  max_leak_ratio: "최대 누설률 (0~1)",
  max_offset_c: "최대 센서 오차 (°C)",
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
};

/** Maintenance actions in the order they appear on the HMI. */
export const MAINTENANCE_ACTIONS = Object.keys(ACTION_LABEL);
