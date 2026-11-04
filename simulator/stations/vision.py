from simulator.alarms import MachineAlarm
from simulator.stations.base import Station


class Vision(Station):
    """Lifts the housing off the belt, pushes it against datum pins, then measures the remaining offset.

    The residual offset is handed to the dispenser, which shifts its bead path by it.
    """

    name = "VISION"
    SEQUENCE = [
        ("TRANSFER_IN", 1.0, ""),
        ("LIFT_UP", 0.4, ""),
        ("PUSH_ALIGN", 0.4, ""),
        ("SETTLE", 0.2, ""),
        ("CAPTURE", 0.3, ""),
        ("PROCESS", 0.2, ""),
        ("RELEASE", 0.3, ""),
        ("LIFT_DOWN", 0.4, ""),
    ]

    def process(self):
        if self.m.run_mode == "DRY":
            # No part to look at: the cylinders still go through their strokes, the camera is not triggered.
            for step, seconds in (("LIFT_UP", 0.4), ("PUSH_ALIGN", 0.4), ("SETTLE", 0.2), ("RELEASE", 0.3), ("LIFT_DOWN", 0.4)):
                yield self.motion(step, seconds, pneumatic=step != "SETTLE")
            return
        rng = self.m.rng
        threshold = self.cfg["score_threshold"]
        mark_defect = rng.random() < self.cfg["mark_defect_probability"]  # damaged or dirty mark on this part

        yield self.motion("LIFT_UP", 0.4, pneumatic=True)
        yield self.motion("PUSH_ALIGN", 0.4, pneumatic=True)
        yield self.motion("SETTLE", 0.2)
        for attempt in range(2):
            yield self.motion("CAPTURE", 0.3)
            yield self.motion("PROCESS", 0.2)
            score = rng.gauss(0.93, 0.015)
            if mark_defect or rng.random() < self.cfg["glitch_probability"]:
                score = rng.uniform(0.35, 0.65)
            if score >= threshold:
                break
            self.log("WARN", "Align mark low score", score=f"{score:.3f}", attempt=attempt + 1)
        else:
            raise MachineAlarm("E2001", f"score={score:.3f} threshold={threshold:.2f}")

        dx = rng.gauss(0.0, 0.03)
        dy = rng.gauss(0.0, 0.03)
        limit = self.cfg["max_offset_mm"]
        if abs(dx) > limit or abs(dy) > limit:
            raise MachineAlarm("E2002", f"dx={dx:+.3f}mm dy={dy:+.3f}mm limit={limit:.2f}mm")
        self.wp.data.update(align_dx_mm=round(dx, 3), align_dy_mm=round(dy, 3), align_score=round(score, 3))
        self.log("INFO", "Align OK", dx=f"{dx:+.3f}mm", dy=f"{dy:+.3f}mm", score=f"{score:.3f}")
        yield self.motion("RELEASE", 0.3, pneumatic=True)
        yield self.motion("LIFT_DOWN", 0.4, pneumatic=True)
