"""Hidden physical state of the cell.

Stations only see this through sensors. Faults change these values directly, and
the ground-truth writer samples them so analysis results can be checked later.
"""
import math
from dataclasses import dataclass
from random import Random

EJECTOR_FULL_AIR_KPA = 450.0     # vacuum ejector reaches full vacuum at or above this supply
REGULATOR_HEADROOM_KPA = 120.0   # dispensing regulator needs this much supply above its output
CYLINDER_FULL_AIR_KPA = 450.0    # air cylinders move slower below this supply


@dataclass
class PlantAir:
    """Factory compressed air: dispensing regulator, the fixture's vacuum ejector and every air cylinder."""

    nominal_kpa: float = 550.0
    drop_kpa: float = 0.0   # set by air-supply faults
    noise_kpa: float = 0.0  # slow natural wander

    @property
    def supply_kpa(self) -> float:
        return self.nominal_kpa - self.drop_kpa + self.noise_kpa

    def update(self, dt: float, rng: Random) -> None:
        self.noise_kpa += -self.noise_kpa * dt / 120.0 + rng.gauss(0.0, 1.5 * math.sqrt(dt))


@dataclass
class FixturePhysics:
    """Vacuum fixture on the dispenser's lift-up unit that holds the housing flat while dispensing."""

    vacuum_supply_kpa: float = -85.0
    leak_ratio: float = 0.0     # 0 = sealed vacuum pad, 1 = no vacuum at all
    ejector_ratio: float = 1.0  # drops when plant air is low

    @property
    def achievable_vacuum_kpa(self) -> float:
        return self.vacuum_supply_kpa * (1.0 - self.leak_ratio) * self.ejector_ratio


@dataclass
class DispenserPhysics:
    temp_setpoint_c: float
    temp_true_c: float
    syringe_capacity_ml: float
    syringe_level_ml: float
    nozzle_open_ratio: float = 1.0
    material_viscosity: float = 1.0  # relative to nominal; varies per material lot
    thickening_per_h: float = 0.025  # pot life: the adhesive slowly thickens after the syringe is mounted
    syringe_age_h: float = 0.0
    regulator_out_kpa: float = 0.0
    needle_z_offset_mm: float = 0.0  # + means the needle tip sits higher than taught
    needle_xy_offset_mm: float = 0.0
    tip_buildup: float = 0.0         # 0..1 adhesive collected on the outside of the needle tip
    bubbles: int = 0                 # air pockets left in the syringe
    bubble_void_probability: float = 0.0
    heater_tau_s: float = 120.0

    def update(self, dt: float, temp_sensor_offset: float) -> None:
        # The heater regulates on the *measured* value, so a biased sensor shifts the true temperature.
        target = self.temp_setpoint_c - temp_sensor_offset
        self.temp_true_c += (target - self.temp_true_c) * min(1.0, dt / self.heater_tau_s)

    def viscosity(self) -> float:
        thickening = 1.0 + self.thickening_per_h * self.syringe_age_h
        return self.material_viscosity * thickening * math.exp(-0.04 * (self.temp_true_c - self.temp_setpoint_c))


@dataclass
class Physics:
    air: PlantAir
    fixture: FixturePhysics
    dispenser: DispenserPhysics

    def update_air_users(self, dispense_setpoint_kpa: float) -> None:
        supply = self.air.supply_kpa
        self.fixture.ejector_ratio = min(1.0, max(0.0, supply / EJECTOR_FULL_AIR_KPA))
        self.dispenser.regulator_out_kpa = max(0.0, min(dispense_setpoint_kpa, supply - REGULATOR_HEADROOM_KPA))

    def cylinder_slowdown(self) -> float:
        """Factor applied to air-cylinder stroke times (1.0 with healthy air)."""
        return max(1.0, CYLINDER_FULL_AIR_KPA / max(self.air.supply_kpa, 100.0))
