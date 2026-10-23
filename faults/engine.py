from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.machine import Machine


class Fault:
    """A hidden problem that changes the machine's physics over time.

    Faults never write fault information to the machine logs. What they did is recorded
    only in the ground truth, so analysis has to find them from symptoms.
    """

    type = ""
    unit = ""
    description = ""
    expected_symptoms: list[str] = []
    resolved_by: frozenset[str] = frozenset()
    defaults: dict = {}

    def __init__(self, fault_id: str, scheduled_at: datetime, params: dict, origin: str = "injected"):
        self.fault_id = fault_id
        self.scheduled_at = scheduled_at
        self.params = {**self.defaults, **params}
        self.origin = origin  # "injected", "natural: ..." or "operator_error: ..."
        self.state = "pending"
        self.injected_at: datetime | None = None
        self.resolved_at: datetime | None = None
        self.resolved_action: str | None = None

    def update(self, machine: Machine, now: datetime) -> None:
        if self.state == "pending" and now >= self.scheduled_at:
            self.state = "active"
            self.injected_at = now
            self.on_start(machine)
        if self.state == "active":
            elapsed = (now - self.injected_at).total_seconds()
            self.apply(machine, elapsed)
            reason = self.self_resolution(machine, elapsed)
            if reason:
                self._resolve(reason, now)

    def on_start(self, machine: Machine) -> None:
        """One-off change when the fault begins (for step faults)."""

    def apply(self, machine: Machine, elapsed_s: float) -> None:
        """Change applied every tick while active (for gradual faults)."""

    def self_resolution(self, machine: Machine, elapsed_s: float) -> str | None:
        """Return a reason if the fault has gone away on its own."""
        return None

    def resolve(self, action: str, now: datetime) -> None:
        if self.state == "active" and action in self.resolved_by:
            self._resolve(action, now)

    def _resolve(self, action: str, now: datetime) -> None:
        self.state = "resolved"
        self.resolved_at = now
        self.resolved_action = action

    def progress(self, elapsed_s: float) -> float:
        if "ramp_min" not in self.params:
            return 1.0
        return min(1.0, elapsed_s / (self.params["ramp_min"] * 60.0))

    def truth(self) -> dict:
        def iso(t):
            return t.isoformat(timespec="milliseconds") if t else None
        return {
            "fault_id": self.fault_id,
            "type": self.type,
            "unit": self.unit,
            "origin": self.origin,
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

    def next_id(self) -> str:
        return f"F{len(self.faults) + 1:03d}"

    def add(self, fault: Fault) -> None:
        self.faults.append(fault)

    def update(self, machine: Machine, now: datetime) -> None:
        for fault in self.faults:
            fault.update(machine, now)

    def on_maintenance(self, action: str, now: datetime) -> None:
        for fault in self.faults:
            fault.resolve(action, now)

    def active(self) -> list[Fault]:
        return [f for f in self.faults if f.state == "active"]
