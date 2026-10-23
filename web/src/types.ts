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
  step_s: number; // duration of the current step in simulated seconds
  progress: number; // 0..1 through the current step when the state was sent
  wp: string | null;
  judge: "" | "OK" | "NG" | null;
}

export interface Sensors {
  timestamp?: string;
  mode?: MachineMode;
  fixture_vac_kpa?: number;
  disp_pressure_kpa?: number;
  disp_valve_open?: number;
  disp_temp_c?: number;
  syringe_level_pct?: number;
}

export interface FaultTruth {
  fault_id: string;
  type: string;
  unit: string;
  origin: string;
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
  recipes: string[];
  fault_types: Record<string, FaultTypeInfo>;
}

/** [epoch ms of simulated time, value] */
export type TrendPoint = [number, number];

export interface TrendLimits {
  lo?: number;
  hi?: number;
}

export interface Trends {
  now: number;
  since: number;
  series: Record<string, { points: TrendPoint[]; limits: TrendLimits }>;
}

export interface HiddenState {
  plant_air_kpa: number;
  regulator_out_kpa: number;
  nozzle_open_ratio: number;
  fixture_leak_ratio: number;
  achievable_vac_kpa: number;
  temp_true_c: number;
  temp_sensor_offset_c: number;
  material_viscosity: number;
  syringe_age_h: number;
  needle_z_offset_mm: number;
  needle_xy_offset_mm: number;
  tip_buildup: number;
  bubbles: number;
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
  ng_buffer: number;
  ng_buffer_capacity: number;
  syringe_level_pct: number;
  syringe_age_min: number;
  cycle_stop: boolean;
  stations: StationView[];
  fixture_vacuum_on: boolean;
  ng_picker_vacuum_on: boolean;
  dispenser_valve_open: boolean;
  sensors: Sensors;
  sim: {
    run_id: string;
    scenario: string;
    speed: number;
    paused: boolean;
    auto_operator: boolean;
  };
  operator: {
    phase: string;
    crew: string[];
  };
  engineer: {
    truth_file: string;
    faults: FaultTruth[];
    hidden: HiddenState;
    setpoint_errors: Record<string, number>;
  };
}
