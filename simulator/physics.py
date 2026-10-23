"""Hidden physical state of the cell.

Stations only see this through sensors. Faults change these values directly, and
the ground-truth writer samples them so analysis results can be checked later.
"""
import math
from dataclasses import dataclass


@dataclass
class LoaderPhysics:
    vacuum_supply_kpa: float = -85.0
    leak_ratio: float = 0.0  # 0 = sealed pick pad, 1 = no vacuum at all

    @property
    def achievable_vacuum_kpa(self) -> float:
        return self.vacuum_supply_kpa * (1.0 - self.leak_ratio)


@dataclass
class DispenserPhysics:
    temp_setpoint_c: float
    temp_true_c: float
    syringe_capacity_ml: float
    syringe_level_ml: float
    nozzle_open_ratio: float = 1.0
    material_viscosity: float = 1.0  # relative to nominal; varies per material lot
    heater_tau_s: float = 120.0

    def update(self, dt: float, temp_sensor_offset: float) -> None:
        # The heater regulates on the *measured* value, so a biased sensor shifts the true temperature.
        target = self.temp_setpoint_c - temp_sensor_offset
        self.temp_true_c += (target - self.temp_true_c) * min(1.0, dt / self.heater_tau_s)

    def viscosity(self) -> float:
        return self.material_viscosity * math.exp(-0.04 * (self.temp_true_c - self.temp_setpoint_c))


@dataclass
class Physics:
    loader: LoaderPhysics
    dispenser: DispenserPhysics
