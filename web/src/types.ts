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
  wait: string; // why the station is not working ("" when it is)
  history: { end: string; step: string; t: number }[]; // newest first
}

export interface LogEntry {
  ts: string;
  level: "DEBUG" | "INFO" | "WARN" | "ALARM";
  unit: string;
  text: string;
}

export interface SequenceStep {
  step: string;
  std_s: number | null;
  condition: string;
}

export type HmiLevel = "GUEST" | "OPERATOR" | "ENGINEER" | "MAKER";

export interface ManualDevice {
  id: string;
  unit: string;
  kind: "cylinder" | "vacuum" | "belt";
  position: number; // 0 = home/off, 1 = extended/on
  target: number;
  home_sensor: boolean;
  work_sensor: boolean;
  kpa?: number; // vacuum devices only
}

export interface ManualAxis {
  id: string;
  unit: string;
  position: number; // mm
  target: number;
  min: number;
  max: number;
  home: number;
  presets: Record<string, number>;
  moving: boolean;
}

export interface Metrics {
  uph: number;
  tact_s: number | null;
  seconds: Partial<Record<"RUNNING" | "STOPPED" | "ALARM" | "STARVED" | "BLOCKED", number>>;
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
  sequences: Record<string, SequenceStep[]>;
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
  op_mode: "AUTO" | "MANUAL";
  hmi: {
    user: { id: string; name: string } | null;
    level: HmiLevel;
    permissions: Record<string, boolean>; // action -> allowed for the current level
    users: { id: string; name: string; level: HmiLevel }[];
    maintenance_level: Record<string, HmiLevel>; // maintenance actions that need more than OPERATOR
  };
  init: { state: "REQUIRED" | "RUNNING" | "DONE"; step: string; progress: number };
  safety: { estop: boolean; doors_open: Record<string, boolean>; problems: string[] };
  manual: { devices: ManualDevice[]; axes: ManualAxis[] } | null; // only in MANUAL
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
  metrics: Metrics;
  live_log: LogEntry[]; // INFO and above, newest first
  setpoints: Record<string, number>;
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
