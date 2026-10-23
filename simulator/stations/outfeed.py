from simulator.alarms import MachineAlarm
from simulator.stations.base import Station


class Outfeed(Station):
    """Hands OK parts to the downstream machine; a small vacuum picker moves NG parts into the NG buffer."""

    name = "OUTFEED"
    SEQUENCE = [
        ("TRANSFER_IN", 1.0, ""),
        ("WAIT_DOWNSTREAM", None, "ok"),
        ("STOPPER_DOWN", 0.15, "ok"),
        ("TRANSFER_OUT", 1.0, "ok"),
        ("PICK_DOWN", 0.3, "ng"),
        ("VACUUM_ON", 0.2, "ng"),
        ("PICK_UP", 0.3, "ng"),
        ("MOVE_TO_NG", 0.8, "ng"),
        ("PLACE", 0.3, "ng"),
        ("RETURN", 0.8, "ng"),
    ]

    def __init__(self, machine, cfg):
        super().__init__(machine, cfg)
        self.ng_count = 0
        self.picker_vacuum = False

    def process(self):
        if self.wp.judge == "OK":
            yield from self._send_downstream()
        else:
            yield from self._move_to_ng_buffer()

    def _send_downstream(self):
        rng = self.m.rng
        cfg = self.cfg
        if rng.random() < cfg["downstream_stop_probability"]:
            wait = rng.uniform(*cfg["downstream_stop_min"]) * 60.0
        elif rng.random() < cfg["downstream_busy_probability"]:
            wait = rng.uniform(*cfg["downstream_busy_s"])
        else:
            wait = 0.0
        if wait > 0:
            self.log("INFO", "Waiting for downstream")
            yield self.motion("WAIT_DOWNSTREAM", wait, jitter=0.0)
            self.log("INFO", "Downstream ready", waited=f"{wait:.1f}s")
        yield self.motion("STOPPER_DOWN", 0.15, pneumatic=True)
        yield self.motion("TRANSFER_OUT", 1.0)
        self.log("INFO", "Part sent downstream")

    def _move_to_ng_buffer(self):
        capacity = self.cfg["ng_buffer_capacity"]
        if self.ng_count >= capacity:
            raise MachineAlarm("E5001", f"count={self.ng_count}/{capacity}")
        yield self.motion("PICK_DOWN", 0.3, pneumatic=True)
        self.picker_vacuum = True
        yield self.motion("VACUUM_ON", 0.2)
        yield self.motion("PICK_UP", 0.3, pneumatic=True)
        yield self.motion("MOVE_TO_NG", 0.8)
        yield self.motion("PLACE", 0.3, pneumatic=True)
        self.picker_vacuum = False
        self.ng_count += 1
        self.log("INFO", "NG part to buffer", reason=self.wp.ng_reason, buffer=f"{self.ng_count}/{capacity}")
        yield self.motion("RETURN", 0.8)
