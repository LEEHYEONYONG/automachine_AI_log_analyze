from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.machine import Machine


class Fault:
    """A hidden problem that changes the machine's physics over time.

    Faults never write to the machine logs. What they did is recorded only in the
    ground truth, so analysis has to find them from symptoms.
    """

    type = ""
    unit = ""
    description = ""
    expected_symptoms: list[str] = []
    resolved_by: frozenset[str] = frozenset()
    defaults: dict = {}

    def __init__(self, fault_id: str, scheduled_at: datetime, params: dict):
        self.fault_id = fault_id
        self.scheduled_at = scheduled_at
        self.params = {**self.defaults, **params}
        self.state = "pending"
        self.injected_at: datetime | None = None
        self.resolved_at: datetime | None = None
        self.resolved_action: str | None = None

    def update(self, machine: Machine, now: datetime) -> None:
        if self.state == "pending" and now >= self.scheduled_at:
            self.state = "active"
            self.injected_at = now
        if self.state == "active":
            self.apply(machine, (now - self.injected_at).total_seconds())

    def apply(self, machine: Machine, elapsed_s: float) -> None:
        raise NotImplementedError

    def resolve(self, action: str, now: datetime) -> None:
        if self.state == "active" and action in self.resolved_by:
            self.state = "resolved"
            self.resolved_at = now
            self.resolved_action = action

    def progress(self, elapsed_s: float) -> float:
        return min(1.0, elapsed_s / (self.params["ramp_min"] * 60.0))

    def truth(self) -> dict:
        def iso(t):
            return t.isoformat(timespec="milliseconds") if t else None
        return {
            "fault_id": self.fault_id,
            "type": self.type,
            "unit": self.unit,
            "description": self.description,
            "params": self.params,
            "scheduled_at": iso(self.scheduled_at),
            "injected_at": iso(self.injected_at),
            "resolved_at": iso(self.resolved_at),
            "resolved_by": self.resolved_action,
            "state_at_end": self.state,
            "expected_symptoms": self.expected_symptoms,
        }


class FaultEngine:
    def __init__(self, faults: list[Fault]):
        self.faults = faults

    def update(self, machine: Machine, now: datetime) -> None:
        for fault in self.faults:
            fault.update(machine, now)

    def on_maintenance(self, action: str, now: datetime) -> None:
        for fault in self.faults:
            fault.resolve(action, now)

    def active(self) -> list[Fault]:
        return [f for f in self.faults if f.state == "active"]
