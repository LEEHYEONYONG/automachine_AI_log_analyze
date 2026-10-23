import math

from simulator.alarms import MachineAlarm
from simulator.stations.base import Station


class Inspection(Station):
    """Line-scan camera that measures bead width and position and looks for defects."""

    name = "INSPECTION"
    SEQUENCE = [
        ("TRANSFER_IN", 1.0, ""),
        ("SCAN", 1.2, ""),
        ("SCAN_RETURN", 0.5, ""),
    ]

    def __init__(self, machine, cfg):
        super().__init__(machine, cfg)
        self.consecutive_ng = 0

    def process(self):
        if self.wp.judge == "NG":
            # Already rejected upstream (e.g. by an initialization); do not overwrite that judgement.
            self.log("INFO", "Skip inspection: already NG", reason=self.wp.ng_reason)
            return

        r = self.m.recipe
        rng = self.m.rng
        hidden = self.wp.hidden
        lo, hi = r["bead_width_spec_mm"]
        max_offset = self.cfg["max_bead_offset_mm"]

        # The line-scan sensor rides an axis across the stopped part, then returns while the image is processed.
        yield self.motion("SCAN", 1.2)
        yield self.motion("SCAN_RETURN", 0.5)
        # A needle sitting too high lays a thinner bead; too low squashes it wider.
        gap_factor = max(0.5, 1.0 - 2.5 * hidden["gap_error_mm"])
        base = self.m.recipe_base[r["name"]]  # physics: width follows weight the same way whatever the recipe says
        width = (base["nominal_bead_width_mm"] * math.sqrt(hidden["bead_weight_mg"] / base["target_bead_weight_mg"])
                 * gap_factor * rng.gauss(1.0, 0.01))
        width = round(width, 3)
        offset = round(abs(hidden["xy_offset_mm"] + rng.gauss(0.0, 0.015)), 3)

        if hidden["bead_break"]:
            reason = "BEAD_BREAK"
        elif hidden["bead_void"]:
            reason = "BEAD_VOID"
        elif hidden["stringing"]:
            reason = "STRINGING"
        elif width < lo:
            reason = "WIDTH_LOW"
        elif width > hi:
            reason = "WIDTH_HIGH"
        elif offset > max_offset:
            reason = "BEAD_OFFSET"
        elif rng.random() < self.cfg["random_defect_probability"]:
            reason = "PARTICLE"
        else:
            reason = ""

        self.wp.data.update(bead_width_mm=width, bead_offset_mm=offset)
        self.wp.judge = "NG" if reason else "OK"
        self.wp.ng_reason = reason
        if reason:
            self.consecutive_ng += 1
            self.log("WARN", "Bead NG", reason=reason, width=f"{width:.3f}mm", offset=f"{offset:.3f}mm")
        else:
            self.consecutive_ng = 0
            self.log("INFO", "Bead OK", width=f"{width:.3f}mm", offset=f"{offset:.3f}mm")

        limit = self.cfg["max_consecutive_ng"]
        if self.consecutive_ng >= limit:
            self.consecutive_ng = 0
            raise MachineAlarm("E4001", f"consecutive_ng={limit} last={reason}", reason=reason)
