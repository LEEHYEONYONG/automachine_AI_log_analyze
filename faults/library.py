from faults.engine import Fault


class NozzleClog(Fault):
    type = "nozzle_clog"
    unit = "DISPENSER"
    description = "Adhesive cures inside the nozzle tip and narrows the flow path."
    expected_symptoms = [
        "weight check value trends down, then E3005",
        "bead width trends down, WIDTH_LOW / BEAD_BREAK NG, possibly E4001",
        "dispensing pressure sag slightly smaller",
    ]
    resolved_by = frozenset({"nozzle_clean", "call_engineer"})
    defaults = {"ramp_min": 180, "min_open_ratio": 0.7}

    def apply(self, machine, elapsed_s):
        closed = (1.0 - self.params["min_open_ratio"]) * self.progress(elapsed_s) ** 1.5
        machine.physics.dispenser.nozzle_open_ratio = 1.0 - closed


class VacuumLeak(Fault):
    type = "vacuum_leak"
    unit = "DISPENSER"
    description = "The vacuum pad on the dispenser's fixture wears and leaks, so the housing is held less firmly."
    expected_symptoms = [
        "fixture vacuum (Dispense done vac=) trends toward the threshold",
        "intermittent 'Fixture vacuum not reached' retries with RESEAT steps",
        "E3001 that keeps coming back after vacuum_check",
    ]
    resolved_by = frozenset({"replace_vacuum_pad"})
    defaults = {"ramp_min": 240, "max_leak_ratio": 0.4}

    def apply(self, machine, elapsed_s):
        machine.physics.fixture.leak_ratio = self.params["max_leak_ratio"] * self.progress(elapsed_s)


class TempSensorDrift(Fault):
    type = "temp_sensor_drift"
    unit = "DISPENSER"
    description = ("The syringe thermocouple reads high. The heater controls to the wrong value, "
                   "so the adhesive runs colder and thicker while the displayed temperature looks normal.")
    expected_symptoms = [
        "displayed syringe temperature stays at the setpoint",
        "weight check value trends down, then E3005",
        "E3005 not fixed by nozzle_clean or replace_syringe",
    ]
    resolved_by = frozenset({"call_engineer"})
    defaults = {"ramp_min": 240, "max_offset_c": 6.0}

    def apply(self, machine, elapsed_s):
        machine.sensors["disp_temp"].offset = self.params["max_offset_c"] * self.progress(elapsed_s)


class AirBubble(Fault):
    type = "air_bubble"
    unit = "DISPENSER"
    description = "Air pockets trapped in the syringe (often when it is changed) leave gaps in the bead."
    expected_symptoms = [
        "scattered BEAD_VOID NG, usually soon after a syringe change",
        "weight check values become noisier and may dip",
        "clears after purge, a new syringe, or once the bubbles have been dispensed out",
    ]
    resolved_by = frozenset({"purge", "replace_syringe"})
    defaults = {"bubbles": 12, "void_probability": 0.15}

    def on_start(self, machine):
        d = machine.physics.dispenser
        d.bubbles += int(self.params["bubbles"])
        d.bubble_void_probability = self.params["void_probability"]

    def self_resolution(self, machine, elapsed_s):
        return "self: bubbles dispensed out" if machine.physics.dispenser.bubbles <= 0 else None


class NeedleTipBuildup(Fault):
    type = "needle_tip_buildup"
    unit = "DISPENSER"
    description = "Adhesive collects on the outside of the needle tip and drags a string when the needle lifts."
    expected_symptoms = [
        "STRINGING NG rate rises over time",
        "E4001 with last=STRINGING",
        "weight and width stay normal",
    ]
    resolved_by = frozenset({"nozzle_clean", "call_engineer"})
    defaults = {"ramp_min": 120, "max_buildup": 0.8}

    def apply(self, machine, elapsed_s):
        machine.physics.dispenser.tip_buildup = self.params["max_buildup"] * self.progress(elapsed_s)


class NeedleOffset(Fault):
    type = "needle_offset"
    unit = "DISPENSER"
    description = ("The needle tip no longer sits where it was taught (re-mounted without calibration, "
                   "a bump, or a changeover). The height laser measures the part, so it cannot see this.")
    expected_symptoms = [
        "step change in bead width (needle high: narrower, needle low: wider)",
        "step change in bead offset, BEAD_OFFSET NG when beyond spec",
        "starts right after a nozzle clean or model change",
    ]
    resolved_by = frozenset({"needle_calibration", "call_engineer"})
    defaults = {"dz_mm": 0.06, "dxy_mm": 0.0}

    def on_start(self, machine):
        d = machine.physics.dispenser
        d.needle_z_offset_mm += self.params["dz_mm"]
        d.needle_xy_offset_mm += self.params["dxy_mm"]


class AirSupplyDrop(Fault):
    type = "air_supply_drop"
    unit = "PLANT"
    description = ("Factory compressed air sags for a while. The dispensing regulator, the fixture's vacuum "
                   "ejector and every air cylinder share it, so several symptoms appear at once. "
                   "It recovers on its own.")
    expected_symptoms = [
        "dispensing pressure reading drops below the setpoint",
        "fixture vacuum weakens at the same time, vacuum retries / E3001",
        "air-cylinder steps (LIFT_UP, PUSH_ALIGN, STOPPER ...) take longer in event.log",
        "weight check low / E3005, then everything recovers without a real fix",
        "E9001 only if the supply falls below the pressure switch",
    ]
    defaults = {"min_supply_kpa": 330.0, "ramp_min": 5.0, "hold_min": 30.0}

    def _shape(self, elapsed_s):
        ramp = self.params["ramp_min"] * 60.0
        hold = self.params["hold_min"] * 60.0
        if elapsed_s < ramp:
            return elapsed_s / ramp
        if elapsed_s < ramp + hold:
            return 1.0
        return max(0.0, 1.0 - (elapsed_s - ramp - hold) / ramp)

    def apply(self, machine, elapsed_s):
        air = machine.physics.air
        air.drop_kpa = (air.nominal_kpa - self.params["min_supply_kpa"]) * self._shape(elapsed_s)

    def self_resolution(self, machine, elapsed_s):
        total = (2 * self.params["ramp_min"] + self.params["hold_min"]) * 60.0
        if elapsed_s >= total:
            machine.physics.air.drop_kpa = 0.0
            return "self: plant air recovered"
        return None

    def progress(self, elapsed_s):
        total = (2 * self.params["ramp_min"] + self.params["hold_min"]) * 60.0
        return min(1.0, elapsed_s / total)


class RecipePressureError(Fault):
    type = "recipe_pressure_error"
    unit = "DISPENSER"
    description = "A wrong dispensing pressure was typed into the recipe."
    expected_symptoms = [
        "a 'Recipe parameter changed' line in event.log right before the change",
        "dispensing pressure reading steps to the new value",
        "weight check and bead width step down (or up)",
    ]
    resolved_by = frozenset({"call_engineer", "model_change"})
    defaults = {"wrong_pressure_kpa": 205.0}

    def on_start(self, machine):
        machine.set_param("dispense_pressure_kpa", self.params["wrong_pressure_kpa"], by=machine.current_operator)


class RecipeRetractError(Fault):
    type = "recipe_retract_error"
    unit = "DISPENSER"
    description = "The dwell before the needle lifts was set to 0, so the adhesive strings."
    expected_symptoms = [
        "a 'Recipe parameter changed' line for retract_delay_s",
        "the DWELL step disappears from the dispenser sequence",
        "STRINGING NG jumps right after the change",
    ]
    resolved_by = frozenset({"call_engineer", "model_change"})
    defaults = {"wrong_retract_delay_s": 0.0}

    def on_start(self, machine):
        machine.set_param("retract_delay_s", self.params["wrong_retract_delay_s"], by=machine.current_operator)


FAULT_TYPES = {cls.type: cls for cls in [
    NozzleClog, VacuumLeak, TempSensorDrift,
    AirBubble, NeedleTipBuildup, NeedleOffset, AirSupplyDrop,
    RecipePressureError, RecipeRetractError,
]}
