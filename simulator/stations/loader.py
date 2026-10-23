from simulator.alarms import MachineAlarm
from simulator.stations.base import Station


class Loader(Station):
    """Picks a housing from the input magazine with a vacuum pad and places it on the conveyor."""

    name = "LOADER"
    transfer_s = 0.0

    def __init__(self, machine, cfg):
        super().__init__(machine, cfg)
        self.magazine = cfg["magazine_capacity"]
        self.vacuum_on = False

    def process(self):
        if self.magazine <= 0:
            raise MachineAlarm("E1002", "magazine=0")
        threshold = self.cfg["vacuum_threshold_kpa"]
        retries = self.cfg["max_pick_retries"]
        for attempt in range(retries + 1):
            yield self.motion("MOVE_TO_PICK", 0.6)
            yield self.motion("PICK_DOWN", 0.3)
            self.vacuum_on = True
            yield self.motion("VACUUM_ON", 0.2)
            vac = self.m.sensors["loader_vac"].read(self.m.physics.loader.achievable_vacuum_kpa, self.m.rng)
            if vac <= threshold:
                break
            self.vacuum_on = False
            self.log("WARN", "Pick vacuum not reached", vac=f"{vac:.1f}kPa",
                     threshold=f"{threshold:.1f}kPa", attempt=attempt + 1)
            yield self.motion("PICK_UP", 0.3)
        else:
            raise MachineAlarm("E1001", f"vac={vac:.1f}kPa threshold={threshold:.1f}kPa retries={retries}")

        self.magazine -= 1
        self.wp = self.m.new_workpiece()
        self.wp.data.update(pick_vac_kpa=vac, pick_retries=attempt)
        self.log("INFO", "Pick OK", vac=f"{vac:.1f}kPa", retries=attempt, magazine=self.magazine)
        yield self.motion("PICK_UP", 0.3)
        yield self.motion("MOVE_TO_PLACE", 0.8)
        yield self.motion("PLACE", 0.4)
        self.vacuum_on = False
