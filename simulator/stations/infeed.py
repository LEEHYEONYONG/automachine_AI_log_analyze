from simulator.alarms import MachineAlarm
from simulator.stations.base import Station


class Infeed(Station):
    """Takes housings from the upstream machine's conveyor (SMEMA-style handshake) and reads their 2D code."""

    name = "INFEED"
    transfer_s = 0.0  # the transfer from upstream is part of the sequence below
    SEQUENCE = [
        ("WAIT_UPSTREAM", None, "upstream_late"),
        ("TRANSFER_IN", 1.0, ""),
        ("STOPPER", 0.15, ""),
        ("ID_READ", 0.3, ""),
    ]

    def process(self):
        if self.m.run_mode != "PRODUCTION":
            yield from self._test_run()
            return
        rng = self.m.rng
        cfg = self.cfg

        # The upstream machine is not always ready to hand over a part.
        if rng.random() < cfg["upstream_stop_probability"]:
            wait = rng.uniform(*cfg["upstream_stop_min"]) * 60.0
        elif rng.random() < cfg["upstream_late_probability"]:
            wait = rng.uniform(*cfg["upstream_late_s"])
        else:
            wait = 0.0
        if wait > 0:
            self.log("INFO", "Waiting for upstream")
            yield self.motion("WAIT_UPSTREAM", wait, jitter=0.0)
            self.log("INFO", "Upstream ready", waited=f"{wait:.1f}s")

        self.wp = self.m.new_workpiece()  # the part is on its way in from here on
        yield self.motion("TRANSFER_IN", 1.0)
        yield self.motion("STOPPER", 0.15, pneumatic=True)

        for attempt in range(2):
            yield self.motion("ID_READ", 0.3)
            if rng.random() >= cfg["id_read_fail_probability"]:
                break
            self.log("WARN", "2D code read fail", attempt=attempt + 1)
        else:
            raise MachineAlarm("E1001", "no read after 2 attempts")
        self.log("INFO", "Part received", serial=self.wp.wp_id)

    def _test_run(self):
        """Dry run: no part and no upstream handshake. Dummy run: the engineer loads dummy parts by hand,
        and their code labels are clean, so the read does not fail."""
        self.wp = self.m.new_workpiece()
        yield self.motion("TRANSFER_IN", 1.0)
        yield self.motion("STOPPER", 0.15, pneumatic=True)
        if self.m.run_mode == "DUMMY":
            yield self.motion("ID_READ", 0.3)
            self.log("INFO", "Dummy part received", serial=self.wp.wp_id)
