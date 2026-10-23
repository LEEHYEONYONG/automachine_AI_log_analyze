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

/** Maintenance actions in the order they appear on the HMI. */
export const MAINTENANCE_ACTIONS = Object.keys(ACTION_LABEL);
