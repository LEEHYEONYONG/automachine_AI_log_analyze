from dataclasses import dataclass
from random import Random


@dataclass
class Sensor:
    noise_std: float
    decimals: int = 2
    offset: float = 0.0  # measurement bias; sensor-drift faults change this

    def read(self, true_value: float, rng: Random) -> float:
        return round(true_value + self.offset + rng.gauss(0.0, self.noise_std), self.decimals)
