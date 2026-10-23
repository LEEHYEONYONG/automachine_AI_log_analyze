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
    unit = "LOADER"
    description = "The loader pick pad wears and leaks, weakening pick vacuum."
    expected_symptoms = [
        "pick vacuum (Pick OK vac=) trends toward the threshold",
        "intermittent 'Pick vacuum not reached' retries",
        "E1001 that keeps coming back after vacuum_check",
    ]
    resolved_by = frozenset({"replace_pick_pad"})
    defaults = {"ramp_min": 240, "max_leak_ratio": 0.4}

    def apply(self, machine, elapsed_s):
        machine.physics.loader.leak_ratio = self.params["max_leak_ratio"] * self.progress(elapsed_s)


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


FAULT_TYPES = {cls.type: cls for cls in [NozzleClog, VacuumLeak, TempSensorDrift]}
