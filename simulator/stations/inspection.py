import math

from simulator.alarms import MachineAlarm
from simulator.stations.base import Station


class Inspection(Station):
    """Line-scan camera that measures bead width and looks for breaks."""

    name = "INSPECTION"

    def __init__(self, machine, cfg):
        super().__init__(machine, cfg)
        self.consecutive_ng = 0

    def process(self):
        r = self.m.recipe
        rng = self.m.rng
        lo, hi = r["bead_width_spec_mm"]

        yield self.motion("SCAN", 1.2)
        weight = self.wp.hidden["bead_weight_mg"]
        width = r["nominal_bead_width_mm"] * math.sqrt(weight / r["target_bead_weight_mg"]) * rng.gauss(1.0, 0.01)
        width = round(width, 3)

        if self.wp.hidden["bead_break"]:
            reason = "BEAD_BREAK"
        elif width < lo:
            reason = "WIDTH_LOW"
        elif width > hi:
            reason = "WIDTH_HIGH"
        elif rng.random() < self.cfg["random_defect_probability"]:
            reason = "BUBBLE"
        else:
            reason = ""

        self.wp.data["bead_width_mm"] = width
        self.wp.judge = "NG" if reason else "OK"
        self.wp.ng_reason = reason
        if reason:
            self.consecutive_ng += 1
            self.log("WARN", "Bead NG", reason=reason, width=f"{width:.3f}mm", spec=f"{lo:.2f}-{hi:.2f}mm")
        else:
            self.consecutive_ng = 0
            self.log("INFO", "Bead OK", width=f"{width:.3f}mm")

        limit = self.cfg["max_consecutive_ng"]
        if self.consecutive_ng >= limit:
            self.consecutive_ng = 0
            raise MachineAlarm("E4001", f"consecutive_ng={limit} last={reason}")
