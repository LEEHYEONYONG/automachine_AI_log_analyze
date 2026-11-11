import { localized } from "../prefs";

// Where each cause the code decides (analysis/app/foreman.py) lives on the dispenser station.
// Same parts as docs/manual/devices: the needle, the heated syringe, the vacuum fixture, the controller and its air.
const CAUSE_DEVICE = {
  nozzle_clog: "needle",
  needle_tip_buildup: "needle",
  needle_offset: "needle",
  air_bubble: "syringe",
  temp_sensor_drift: "syringe",
  vacuum_leak: "fixture",
  air_supply_drop: "controller",
  recipe_pressure_error: "controller",
  recipe_retract_error: "controller",
};

// When only the guard went off the cause has no name, but the value that moved still points at a part.
const GUARD_DEVICE = {
  bead_width_mm: "needle",
  bead_offset_mm: "needle",
  disp_pressure_kpa: "controller",
  vacuum_kpa: "fixture",
};

export const DEVICE_LABEL = localized({
  needle: "니들·노즐",
  syringe: "시린지·히터",
  fixture: "진공 지그",
  controller: "디스펜서 컨트롤러·에어",
});

// Without a recorded fix, an alert stays on the model until this long after its last evidence (equipment time).
const SHOW_MIN = 30;

/** The newest live alert that still has fresh evidence, and the part it points at. null if none.
 *  An alert the watch marks settled (a fix was done and the evidence stopped) is gone at once. */
export function activeFault(watch) {
  const alert = watch?.alerts?.at(-1);
  if (!alert || alert.settled || !watch.sim_time) return null;
  const age = (new Date(watch.sim_time) - new Date(alert.last_at)) / 60_000;
  if (age > SHOW_MIN) return null;
  const device = CAUSE_DEVICE[alert.cause] ?? alert.guard_values?.map((v) => GUARD_DEVICE[v]).find(Boolean);
  return device ? { device, alert } : null;
}
