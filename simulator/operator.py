from __future__ import annotations

from datetime import datetime, timedelta
from random import Random

from simulator.machine import Machine, MachineMode

# What the operator tries for each alarm. If the same alarm keeps coming back within
# the escalation window, they move one step down the list, like a real line would.
RESPONSE_LADDER = {
    "E1001": ["vacuum_check", "vacuum_check", "replace_pick_pad"],
    "E1002": ["supply_magazine"],
    "E2001": ["remove_part"],
    "E2002": ["remove_part", "vision_check"],
    "E3002": ["call_engineer"],
    "E3003": ["replace_syringe"],
    "E3005": ["nozzle_clean", "replace_syringe", "call_engineer"],
    "E4001": ["nozzle_clean", "nozzle_clean", "call_engineer"],
    "E5001": ["swap_output_tray"],
}

ACTION_MINUTES = {
    "supply_magazine": (2, 5),
    "swap_output_tray": (2, 4),
    "remove_part": (1, 3),
    "vision_check": (3, 8),
    "vacuum_check": (3, 6),
    "replace_pick_pad": (10, 20),
    "nozzle_clean": (5, 10),
    "replace_syringe": (8, 15),
    "call_engineer": (30, 60),
    "check": (2, 5),
}

ESCALATION_WINDOW = timedelta(minutes=90)


class Operator:
    """Answers alarms with a response delay, picks an action, then resets and restarts the machine."""

    def __init__(self, machine: Machine, rng: Random, names: tuple[str, ...] = ("OP-A", "OP-B")):
        self.m = machine
        self.rng = rng
        self.names = names
        self.enabled = True  # off when a person runs the machine from the HMI
        self.history: list[tuple[datetime, str]] = []
        self._phase: str | None = None
        self._due: datetime | None = None
        self._action = ""
        self._who = ""

    def start_shift(self) -> None:
        self.m.start(by=self.rng.choice(self.names))

    def update(self, now: datetime) -> None:
        if self._phase is None:
            if self.enabled and self.m.mode is MachineMode.ALARM:
                self._phase = "ack"
                self._due = now + timedelta(seconds=self.rng.uniform(15, 180))
            return
        if now < self._due:
            return

        if self._phase == "ack":
            code = self.m.active_alarm[1].code
            self._action = self._choose(code, now)
            self._who = "ENG-01" if self._action == "call_engineer" else self.rng.choice(self.names)
            self.m.log.event("INFO", "OPERATOR", "Alarm acknowledged", code=code, by=self._who, action=self._action)
            # The fix takes effect when work starts, so e.g. the heater can settle before restart.
            self.m.maintenance(self._action, by=self._who)
            lo, hi = ACTION_MINUTES[self._action]
            self._phase = "work"
            self._due = now + timedelta(minutes=self.rng.uniform(lo, hi))
        else:
            self.m.log.event("INFO", "MAINT", "Maintenance done", action=self._action, by=self._who)
            # Someone may have reset the alarm from the HMI in the meantime.
            if self.m.mode is MachineMode.ALARM:
                self.m.reset(by=self._who)
                self.m.start(by=self._who)
            self._phase = None

    def _choose(self, code: str, now: datetime) -> str:
        recent = sum(1 for t, c in self.history if c == code and now - t <= ESCALATION_WINDOW)
        self.history.append((now, code))
        ladder = RESPONSE_LADDER.get(code, ["check"])
        return ladder[min(recent, len(ladder) - 1)]
