from __future__ import annotations

from datetime import datetime, time, timedelta
from random import Random

from simulator.machine import Machine, MachineMode

# What the operator tries for each alarm. For E4001 they look at the NG type first.
# If the same problem keeps coming back within the escalation window, they move one
# step down the list, like a real line would.
RESPONSE_LADDER = {
    "E1001": ["remove_part"],
    "E2001": ["remove_part"],
    "E2002": ["remove_part", "vision_check"],
    "E3001": ["vacuum_check", "vacuum_check", "replace_vacuum_pad"],
    "E3002": ["call_engineer"],
    "E3003": ["replace_syringe"],
    "E3005": ["nozzle_clean", "replace_syringe", "call_engineer"],
    "E3006": ["replace_syringe"],
    "E4001": ["nozzle_clean", "nozzle_clean", "call_engineer"],
    "E4001:BEAD_VOID": ["purge", "replace_syringe", "call_engineer"],
    "E4001:STRINGING": ["nozzle_clean", "call_engineer"],
    "E4001:BEAD_OFFSET": ["needle_calibration", "call_engineer"],
    "E4001:WIDTH_HIGH": ["needle_calibration", "call_engineer"],
    "E5001": ["empty_ng_buffer"],
    "E9001": ["air_check", "air_check", "call_engineer"],
}

ACTION_MINUTES = {
    "empty_ng_buffer": (2, 4),
    "remove_part": (1, 3),
    "vision_check": (3, 8),
    "vacuum_check": (3, 6),
    "replace_vacuum_pad": (10, 20),
    "nozzle_clean": (5, 10),
    "purge": (2, 4),
    "needle_calibration": (5, 10),
    "replace_syringe": (8, 15),
    "air_check": (5, 15),
    "call_engineer": (30, 60),
    "model_change": (15, 25),
    "none": (0.5, 1.5),  # reset without doing anything
    "check": (2, 5),
}

ESCALATION_WINDOW = timedelta(minutes=90)


def _hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


class Operator:
    """The people running the line.

    Answers alarms after a response delay, picks an action from what they see, then
    resets and restarts. Also takes breaks, hands over at shift change, runs scheduled
    model changes, and sometimes makes mistakes.
    """

    def __init__(self, machine: Machine, rng: Random, plant: dict | None = None,
                 mistakes: dict | None = None, schedule: list[dict] | None = None):
        self.m = machine
        self.rng = rng
        plant = plant or {}
        self.breaks = [(_hhmm(a), _hhmm(b)) for a, b in plant.get("breaks", [])]
        self.shifts = sorted((_hhmm(s["start"]), tuple(s["operators"])) for s in plant.get("shifts", []))
        self.mistakes = mistakes or {}
        start = machine.clock.now
        self.changeovers = sorted(
            ({"at": start + timedelta(minutes=e["at_min"]), "recipe": e["recipe"], "done": False}
             for e in (schedule or []) if e.get("type") == "model_change"),
            key=lambda e: e["at"],
        )
        self.enabled = True  # off when a person runs the machine from the HMI
        self.history: list[tuple[datetime, str, str]] = []  # (time, problem key, action)
        self.names = self._crew(start)
        self.m.current_operator = self.names[0]
        self.phase = "idle"  # idle, ack, work, break, changeover_wait
        self._due: datetime | None = None
        self._action = ""
        self._who = ""
        self._break_key: tuple | None = None
        self._changeover: dict | None = None

    def start_shift(self) -> None:
        self.m.start(by=self.names[0])

    def request_model_change(self, recipe: str) -> None:
        self.changeovers.append({"at": self.m.clock.now, "recipe": recipe, "done": False})

    # ---- main loop --------------------------------------------------------------

    def update(self, now: datetime) -> None:
        self._check_shift(now)
        if self.m.op_mode == "MANUAL":
            return  # someone is working on the machine by hand
        if self.phase in ("ack", "work"):
            if now >= self._due:
                self._advance_task(now)
            return
        if self.phase == "break":
            if now >= self._due:
                self.phase = "idle"
                self.m.log.event("INFO", "OPERATOR", "Break end", by=self.names[0])
                if self.m.mode is MachineMode.STOPPED:
                    self.m.start(by=self.names[0])
            return
        if self.phase == "changeover_wait":
            if self.m.mode is MachineMode.STOPPED:
                self._begin_changeover(now)
            elif self.m.mode is MachineMode.ALARM:
                self.phase = "idle"  # deal with the alarm first; the changeover stays pending
            return

        if not self.enabled:
            return
        brk = self._break_window(now)
        if brk and brk != self._break_key:
            self._break_key = brk
            self.phase = "break"
            self._due = datetime.combine(now.date(), brk[2])
            self.m.log.event("INFO", "OPERATOR", "Break start", by=self.names[0])
            self.m.cycle_stop(by=self.names[0], reason="break")
            return
        if self.m.mode is MachineMode.ALARM:
            self.phase = "ack"
            self._due = now + timedelta(seconds=self.rng.uniform(15, 180))
            return
        pending = next((c for c in self.changeovers if not c["done"] and c["at"] <= now), None)
        if pending:
            self._changeover = pending
            self.phase = "changeover_wait"
            self.m.cycle_stop(by=self.names[0], reason="model_change")

    # ---- tasks ------------------------------------------------------------------

    def _advance_task(self, now: datetime) -> None:
        if self.phase == "ack":
            _, alarm = self.m.active_alarm
            self._action = self._choose(alarm.code, alarm.reason, now)
            self._who = "ENG-01" if self._action == "call_engineer" else self.rng.choice(self.names)
            self.m.log.event("INFO", "OPERATOR", "Alarm acknowledged", code=alarm.code, by=self._who,
                             action=self._action)
            # The fix takes effect when work starts, so e.g. the heater can settle before restart.
            if self._action != "none":
                self.m.maintenance(self._action, by=self._who)
            self._start_work(now)
            return

        if self._action == "model_change":
            self.m.log.event("INFO", "OPERATOR", "Model change done", recipe=self.m.recipe["name"], by=self._who)
        elif self._action != "none":
            self.m.log.event("INFO", "MAINT", "Maintenance done", action=self._action, by=self._who)
        # Someone may have reset the alarm from the HMI in the meantime.
        if self.m.mode is MachineMode.ALARM:
            self.m.reset(by=self._who)
        if self.m.mode is MachineMode.STOPPED:
            self.m.start(by=self._who)
        self.phase = "idle"

    def _begin_changeover(self, now: datetime) -> None:
        change = self._changeover
        change["done"] = True
        self._action = "model_change"
        self._who = self.names[0]
        self.m.log.event("INFO", "OPERATOR", "Model change start", recipe=change["recipe"], by=self._who)
        self.m.change_recipe(change["recipe"], by=self._who)
        self._start_work(now)

    def _start_work(self, now: datetime) -> None:
        lo, hi = ACTION_MINUTES[self._action]
        self.phase = "work"
        self._due = now + timedelta(minutes=self.rng.uniform(lo, hi))

    def _choose(self, code: str, reason: str, now: datetime) -> str:
        key = f"{code}:{reason}" if f"{code}:{reason}" in RESPONSE_LADDER else code
        ladder = RESPONSE_LADDER.get(key, ["check"])
        # Resets without a fix don't count as an attempt; the next try starts from the top again.
        recent = sum(1 for t, k, a in self.history if k == key and a != "none" and now - t <= ESCALATION_WINDOW)
        if len(ladder) > 1 and recent == 0 and self.rng.random() < self.mistakes.get("reset_only_probability", 0.0):
            action = "none"
        else:
            action = ladder[min(recent, len(ladder) - 1)]
        self.history.append((now, key, action))
        return action

    # ---- schedule ---------------------------------------------------------------

    def _crew(self, now: datetime) -> tuple[str, ...]:
        if not self.shifts:
            return ("OP-A", "OP-B")
        current = [ops for start, ops in self.shifts if start <= now.time()]
        return current[-1] if current else self.shifts[-1][1]  # before the first start: night shift

    def _check_shift(self, now: datetime) -> None:
        crew = self._crew(now)
        if crew != self.names:
            self.names = crew
            self.m.current_operator = crew[0]
            self.m.log.event("INFO", "OPERATOR", "Shift change", operators=",".join(crew))

    def _break_window(self, now: datetime) -> tuple | None:
        t = now.time()
        for start, end in self.breaks:
            if start <= t < end:
                return (now.date(), start, end)
        return None
