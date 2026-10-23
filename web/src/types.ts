// Mirrors the JSON pushed by server/runner.py SimRunner.state().

export type MachineMode = "STOPPED" | "RUNNING" | "ALARM";
export type StationState = "IDLE" | "BUSY" | "DONE" | "ALARM";

export interface AlarmEntry {
  set_at: string;
  cleared_at: string | null;
  code: string;
  unit: string;
  text: string;
  detail: string;
}

export interface StationView {
  name: string;
  state: StationState;
  step: string;
  wp: string | null;
}

export interface Sensors {
  timestamp?: string;
  mode?: MachineMode;
  loader_vac_kpa?: number;
  disp_pressure_kpa?: number;
  disp_valve_open?: number;
  disp_temp_c?: number;
  syringe_level_pct?: number;
}

export interface FaultTruth {
  fault_id: string;
  type: string;
  unit: string;
  injected_at: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  state_at_end: string;
  params: Record<string, number>;
}

export interface MachineState {
  time: string;
  machine_id: string;
  recipe: string;
  mode: MachineMode;
  alarm: AlarmEntry | null;
  alarm_history: AlarmEntry[];
  lot: string | null;
  counts: { OK: number; NG: number };
  magazine: number;
  magazine_capacity: number;
  tray_count: number;
  tray_capacity: number;
  syringe_level_pct: number;
  stations: StationView[];
  sensors: Sensors;
  sim: {
    run_id: string;
    scenario: string;
    speed: number;
    paused: boolean;
    auto_operator: boolean;
  };
  engineer: {
    faults: FaultTruth[];
    hidden: Record<string, number>;
  };
}
