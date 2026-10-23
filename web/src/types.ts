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
  description: string;
  params: Record<string, number>;
  scheduled_at: string;
  injected_at: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  state_at_end: "pending" | "active" | "resolved";
  expected_symptoms: string[];
  progress: number;
}

export interface FaultTypeInfo {
  unit: string;
  description: string;
  defaults: Record<string, number>;
  resolved_by: string[];
}

export interface Meta {
  maintenance_actions: string[];
  scenarios: string[];
  fault_types: Record<string, FaultTypeInfo>;
}

export interface HiddenState {
  nozzle_open_ratio: number;
  pick_leak_ratio: number;
  achievable_vac_kpa: number;
  temp_true_c: number;
  temp_sensor_offset_c: number;
  material_viscosity: number;
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
    truth_file: string;
    faults: FaultTruth[];
    hidden: HiddenState;
  };
}
