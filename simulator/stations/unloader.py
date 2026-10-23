from simulator.alarms import MachineAlarm
from simulator.stations.base import Station


class Unloader(Station):
    """Puts OK parts in the output tray and drops NG parts down the reject chute."""

    name = "UNLOADER"

    def __init__(self, machine, cfg):
        super().__init__(machine, cfg)
        self.tray_count = 0

    def process(self):
        if self.wp.judge != "OK":
            yield self.motion("NG_CHUTE", 0.6)
            self.log("INFO", "Unload NG", reason=self.wp.ng_reason)
            return
        if self.tray_count >= self.cfg["tray_capacity"]:
            raise MachineAlarm("E5001", f"count={self.tray_count}")
        yield self.motion("PICK", 0.4)
        yield self.motion("MOVE_TO_TRAY", 0.8)
        yield self.motion("PLACE", 0.4)
        self.tray_count += 1
        self.log("INFO", "Unload OK", tray=self.tray_count)
