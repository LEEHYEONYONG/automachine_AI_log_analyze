from simulator.alarms import MachineAlarm
from simulator.stations.base import Station


class Dispenser(Station):
    """Air-pulse dispenser on a gantry that draws an adhesive bead along the housing."""

    name = "DISPENSER"

    def __init__(self, machine, cfg):
        super().__init__(machine, cfg)
        self.valve_open = False
        self.need_weight_check = True  # the first shot of a shift is always verified
        self.pieces_since_check = 0

    @property
    def level_pct(self) -> float:
        p = self.m.physics.dispenser
        return 100.0 * p.syringe_level_ml / p.syringe_capacity_ml

    def process(self):
        r = self.m.recipe
        p = self.m.physics.dispenser
        rng = self.m.rng

        if self.level_pct < self.cfg["syringe_low_pct"]:
            raise MachineAlarm("E3003", f"level={self.level_pct:.1f}%")
        temp = self.m.sensors["disp_temp"].read(p.temp_true_c, rng)
        if abs(temp - r["syringe_temp_c"]) > self.cfg["temp_alarm_band_c"]:
            raise MachineAlarm("E3002", f"temp={temp:.2f}C setpoint={r['syringe_temp_c']:.1f}C")
        if self.need_weight_check or self.pieces_since_check >= self.cfg["weight_check_interval"]:
            yield from self._weight_check()

        yield self.motion("APPROACH", 0.8)
        yield self.motion("HEIGHT_MEASURE", 0.5)
        height = self.m.sensors["nozzle_height"].read(r["nozzle_height_mm"], rng)
        self.valve_open = True
        duration = self.motion("DISPENSE", r["dispense_time_s"], jitter=0.005)
        yield duration
        self.valve_open = False
        weight, broken = self._shot(duration)
        pressure = self.m.sensors["disp_pressure"].read(self.dispensing_pressure_kpa(), rng)

        self.wp.hidden.update(bead_weight_mg=weight, bead_break=broken)
        self.wp.data.update(disp_pressure_kpa=pressure, disp_temp_c=temp, nozzle_height_mm=height)
        self.log("INFO", "Dispense done", pressure=f"{pressure:.1f}kPa", temp=f"{temp:.2f}C",
                 height=f"{height:.3f}mm", t=f"{duration:.3f}s", syringe=f"{self.level_pct:.1f}%")
        self.pieces_since_check += 1
        yield self.motion("RETRACT", 0.5)

    def dispensing_pressure_kpa(self) -> float:
        # Line pressure sags while the valve is open; a narrower nozzle draws less flow and sags less.
        p = self.m.physics.dispenser
        return self.m.recipe["dispense_pressure_kpa"] * (1.0 - 0.03 * p.nozzle_open_ratio)

    def _shot(self, duration: float) -> tuple[float, bool]:
        """Dispense for `duration` seconds and return the true bead weight and whether the bead broke."""
        r = self.m.recipe
        p = self.m.physics.dispenser
        rng = self.m.rng
        nominal_flow = r["target_bead_weight_mg"] / r["dispense_time_s"]
        flow = nominal_flow * p.nozzle_open_ratio / p.viscosity()
        weight = max(0.0, flow * duration * rng.gauss(1.0, 0.015))
        p.syringe_level_ml = max(0.0, p.syringe_level_ml - weight / 1000.0 / self.cfg["material_density_g_per_ml"])
        broken = rng.random() < max(0.0, (0.8 - p.nozzle_open_ratio) * 0.5)
        return weight, broken

    def _weight_check(self):
        r = self.m.recipe
        target = r["target_bead_weight_mg"]
        tol = target * r["weight_tolerance_pct"] / 100.0
        lo, hi = target - tol, target + tol

        yield self.motion("MOVE_TO_SCALE", 1.5)
        self.valve_open = True
        duration = self.motion("TEST_SHOT", r["dispense_time_s"], jitter=0.005)
        yield duration
        self.valve_open = False
        weight, _ = self._shot(duration)
        yield self.motion("WEIGH", 3.0)
        measured = round(weight + self.m.rng.gauss(0.0, 0.03), 2)
        self.m.trends.add("weight_check_mg", self.m.clock.now, measured)
        yield self.motion("MOVE_FROM_SCALE", 1.5)

        if not lo <= measured <= hi:
            self.need_weight_check = True
            raise MachineAlarm("E3005", f"weight={measured:.2f}mg spec={lo:.1f}-{hi:.1f}mg")
        self.log("INFO", "Weight check OK", weight=f"{measured:.2f}mg", spec=f"{lo:.1f}-{hi:.1f}mg")
        self.need_weight_check = False
        self.pieces_since_check = 0
