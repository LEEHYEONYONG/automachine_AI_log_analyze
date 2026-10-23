from dataclasses import dataclass

from simulator.alarms import MachineAlarm
from simulator.stations.base import Station


@dataclass
class Shot:
    weight_mg: float
    broken: bool     # bead broken because the nozzle is partly clogged
    void: bool       # an air pocket left a gap in the bead
    stringing: bool  # adhesive tail dragged across the part when the needle lifted


class Dispenser(Station):
    """Air-pulse dispenser on a gantry that draws an adhesive bead along the housing."""

    name = "DISPENSER"
    SEQUENCE = [
        ("TRANSFER_IN", 1.0, ""),
        ("MOVE_TO_SCALE", 1.5, "weight_check"),
        ("TEST_SHOT", None, "weight_check"),
        ("WEIGH", 3.0, "weight_check"),
        ("MOVE_FROM_SCALE", 1.5, "weight_check"),
        ("LIFT_UP", 0.4, ""),
        ("VACUUM_ON", 0.3, ""),
        ("RESEAT", 0.6, "retry"),
        ("APPROACH", 0.8, ""),
        ("HEIGHT_MEASURE", 0.5, ""),
        ("DISPENSE", None, ""),
        ("DWELL", None, ""),
        ("RETRACT", 0.5, ""),
        ("VACUUM_OFF", 0.2, ""),
        ("LIFT_DOWN", 0.4, ""),
    ]

    def __init__(self, machine, cfg):
        super().__init__(machine, cfg)
        self.valve_open = False
        self.vacuum_on = False
        self.need_weight_check = True  # the first shot of a shift is always verified
        self.pieces_since_check = 0
        self.syringe_installed_at = machine.clock.now

    @property
    def level_pct(self) -> float:
        p = self.m.physics.dispenser
        return 100.0 * p.syringe_level_ml / p.syringe_capacity_ml

    def process(self):
        sp = self.m.setpoints
        p = self.m.physics.dispenser
        rng = self.m.rng

        if self.level_pct < self.cfg["syringe_low_pct"]:
            raise MachineAlarm("E3003", f"level={self.level_pct:.1f}%")
        if p.syringe_age_h > self.cfg["pot_life_h"]:
            raise MachineAlarm("E3006", f"age={p.syringe_age_h:.1f}h limit={self.cfg['pot_life_h']:.1f}h")
        temp = self.m.sensors["disp_temp"].read(p.temp_true_c, rng)
        if abs(temp - sp["syringe_temp_c"]) > self.cfg["temp_alarm_band_c"]:
            raise MachineAlarm("E3002", f"temp={temp:.2f}C setpoint={sp['syringe_temp_c']:.1f}C")
        if self.need_weight_check or self.pieces_since_check >= self.cfg["weight_check_interval"]:
            yield from self._weight_check()

        # Lift the housing onto the vacuum fixture so it cannot move while the bead is drawn.
        yield self.motion("LIFT_UP", 0.4, pneumatic=True)
        threshold = self.cfg["vacuum_threshold_kpa"]
        retries = self.cfg["max_vacuum_retries"]
        for attempt in range(retries + 1):
            self.vacuum_on = True
            yield self.motion("VACUUM_ON", 0.3)
            vac = self.m.sensors["fixture_vac"].read(self.m.physics.fixture.achievable_vacuum_kpa, rng)
            if vac <= threshold:
                break
            self.vacuum_on = False
            self.log("WARN", "Fixture vacuum not reached", vac=f"{vac:.1f}kPa",
                     threshold=f"{threshold:.1f}kPa", attempt=attempt + 1)
            yield self.motion("RESEAT", 0.6, pneumatic=True)
        else:
            raise MachineAlarm("E3001", f"vac={vac:.1f}kPa threshold={threshold:.1f}kPa retries={retries}")
        self.wp.data.update(fixture_vac_kpa=vac, vac_retries=attempt)

        yield self.motion("APPROACH", 0.8)
        yield self.motion("HEIGHT_MEASURE", 0.5)
        # The laser measures the part surface, so it cannot see a shifted needle tip.
        height = self.m.sensors["nozzle_height"].read(sp["nozzle_height_mm"], rng)
        self.valve_open = True
        duration = self.motion("DISPENSE", sp["dispense_time_s"], jitter=0.005)
        yield duration
        self.valve_open = False
        shot = self._shot(duration)
        pressure = self.m.sensors["disp_pressure"].read(self.dispensing_pressure_kpa(), rng)

        self.wp.hidden.update(
            bead_weight_mg=shot.weight_mg, bead_break=shot.broken, bead_void=shot.void, stringing=shot.stringing,
            # gap vs. the validated recipe: a shifted needle or an edited gap both change the bead
            gap_error_mm=p.needle_z_offset_mm
            + sp["nozzle_height_mm"] - self.m.recipe_base[self.m.recipe["name"]]["nozzle_height_mm"], xy_offset_mm=p.needle_xy_offset_mm,
        )
        self.wp.data.update(disp_pressure_kpa=pressure, disp_temp_c=temp, nozzle_height_mm=height)
        self.log("INFO", "Dispense done", vac=f"{vac:.1f}kPa", pressure=f"{pressure:.1f}kPa", temp=f"{temp:.2f}C",
                 height=f"{height:.3f}mm", t=f"{duration:.3f}s", syringe=f"{self.level_pct:.1f}%",
                 path_offset=f"{self.wp.data.get('align_dx_mm', 0):+.3f}/{self.wp.data.get('align_dy_mm', 0):+.3f}mm")
        self.pieces_since_check += 1
        if sp["retract_delay_s"] > 0:
            yield self.motion("DWELL", sp["retract_delay_s"])
        yield self.motion("RETRACT", 0.5)
        self.vacuum_on = False
        yield self.motion("VACUUM_OFF", 0.2)
        yield self.motion("LIFT_DOWN", 0.4, pneumatic=True)

    def dispensing_pressure_kpa(self) -> float:
        # Line pressure sags while the valve is open; a narrower nozzle draws less flow and sags less.
        p = self.m.physics.dispenser
        return p.regulator_out_kpa * (1.0 - 0.03 * p.nozzle_open_ratio)

    def _shot(self, duration: float) -> Shot:
        """Dispense for `duration` seconds and work out what actually came out."""
        r = self.m.recipe_base[self.m.recipe["name"]]
        p = self.m.physics.dispenser
        rng = self.m.rng
        # Flow constant chosen so the recipe as validated at power-on gives exactly its target weight.
        k = r["target_bead_weight_mg"] / (r["dispense_time_s"] * r["dispense_pressure_kpa"])
        flow = k * p.regulator_out_kpa * p.nozzle_open_ratio / p.viscosity()
        weight = max(0.0, flow * duration * rng.gauss(1.0, 0.015))

        void = False
        if p.bubbles > 0 and rng.random() < p.bubble_void_probability:
            void = True
            p.bubbles -= 1
            weight *= 0.85

        p.syringe_level_ml = max(0.0, p.syringe_level_ml - weight / 1000.0 / self.cfg["material_density_g_per_ml"])
        broken = rng.random() < max(0.0, (0.8 - p.nozzle_open_ratio) * 0.5)
        stringing_p = (0.002 + 0.3 * p.tip_buildup
                       + (0.25 if self.m.setpoints["retract_delay_s"] < 0.1 else 0.0)
                       + 0.1 * max(0.0, 1.0 / p.viscosity() - 1.0))  # runny adhesive strings more
        return Shot(weight, broken, void, rng.random() < stringing_p)

    def _weight_check(self):
        r = self.m.recipe
        target = r["target_bead_weight_mg"]
        tol = target * r["weight_tolerance_pct"] / 100.0
        lo, hi = target - tol, target + tol

        yield self.motion("MOVE_TO_SCALE", 1.5)
        self.valve_open = True
        duration = self.motion("TEST_SHOT", self.m.setpoints["dispense_time_s"], jitter=0.005)
        yield duration
        self.valve_open = False
        shot = self._shot(duration)
        yield self.motion("WEIGH", 3.0)
        measured = round(shot.weight_mg + self.m.rng.gauss(0.0, 0.03), 2)
        self.m.trends.add("weight_check_mg", self.m.clock.now, measured)
        yield self.motion("MOVE_FROM_SCALE", 1.5)

        if not lo <= measured <= hi:
            self.need_weight_check = True
            raise MachineAlarm("E3005", f"weight={measured:.2f}mg spec={lo:.1f}-{hi:.1f}mg")
        self.log("INFO", "Weight check OK", weight=f"{measured:.2f}mg", spec=f"{lo:.1f}-{hi:.1f}mg")
        self.need_weight_check = False
        self.pieces_since_check = 0
