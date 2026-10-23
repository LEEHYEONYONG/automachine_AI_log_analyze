"""Manual-mode devices: the cylinders, vacuums, belts and servo axes an operator can move one by one.

In AUTO the station sequences drive the machine and these models are idle. In MANUAL the HMI
commands them directly, interlocks guard against collisions, and every move is logged.
Positions are in millimetres; the 3D viewer converts them to scene units.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.machine import Machine


class InterlockError(Exception):
    """A manual command that would be unsafe in the current state."""


@dataclass
class Device:
    """A cylinder, vacuum or belt. position 0 = home/off, 1 = extended/on."""

    id: str
    unit: str
    kind: str          # "cylinder", "vacuum" or "belt"
    stroke_s: float
    auto_ready: float  # where it must be before switching back to AUTO
    position: float = 0.0
    target: float = 0.0
    _elapsed: float = 0.0

    @property
    def moving(self) -> bool:
        return self.position != self.target

    def command(self, on: bool) -> None:
        self.target = 1.0 if on else 0.0
        self._elapsed = 0.0

    def update(self, dt: float, slowdown: float) -> float | None:
        """Advance the stroke; returns the stroke time when the device arrives."""
        if not self.moving:
            return None
        self._elapsed += dt
        stroke = max(self.stroke_s * (slowdown if self.kind == "cylinder" else 1.0), 1e-6)
        step = dt / stroke
        self.position = min(self.target, self.position + step) if self.target > self.position \
            else max(self.target, self.position - step)
        return self._elapsed if not self.moving else None

    def view(self) -> dict:
        return {
            "id": self.id, "unit": self.unit, "kind": self.kind,
            "position": round(self.position, 3), "target": self.target,
            "home_sensor": self.position <= 0.02, "work_sensor": self.position >= 0.98,
        }


@dataclass
class Axis:
    id: str
    unit: str
    min_mm: float
    max_mm: float
    speed_mm_s: float
    home_mm: float
    presets: dict[str, float] = field(default_factory=dict)
    position: float = 0.0
    target: float = 0.0

    def __post_init__(self):
        self.position = self.target = self.home_mm

    @property
    def moving(self) -> bool:
        return abs(self.position - self.target) > 1e-6

    def move_to(self, mm: float) -> None:
        if not self.min_mm <= mm <= self.max_mm:
            raise InterlockError(f"{self.id} 이동 범위({self.min_mm:g}~{self.max_mm:g} mm)를 벗어납니다")
        self.target = mm

    def update(self, dt: float) -> bool:
        """Returns True when the axis arrives this tick."""
        if not self.moving:
            return False
        delta = self.target - self.position
        stride = self.speed_mm_s * dt
        self.position = self.target if abs(delta) <= stride else self.position + stride * (1 if delta > 0 else -1)
        return not self.moving

    def view(self) -> dict:
        return {
            "id": self.id, "unit": self.unit, "position": round(self.position, 2), "target": round(self.target, 2),
            "min": self.min_mm, "max": self.max_mm, "home": self.home_mm, "presets": self.presets,
            "moving": self.moving,
        }


SAFE_Z_MM = 80.0      # dispenser Z must be at least this high before X/Y moves
LOW_Z_MM = 30.0       # below this the needle is near the part or the conveyor
SCALE_XY = (150.0, -200.0)
STEPS_LIFT_UP = {
    "VISION": {"PUSH_ALIGN", "SETTLE", "CAPTURE", "PROCESS", "RELEASE"},
    "DISPENSER": {"VACUUM_ON", "RESEAT", "APPROACH", "HEIGHT_MEASURE", "DISPENSE", "DWELL", "RETRACT", "VACUUM_OFF"},
}


class ManualDevices:
    def __init__(self, machine: Machine):
        self.m = machine
        stations = ["INFEED", "VISION", "DISPENSER", "INSPECTION", "OUTFEED"]
        devices = [Device(f"{s}_STOPPER", s, "cylinder", 0.15, auto_ready=1.0) for s in stations]
        devices += [
            Device("VISION_LIFT", "VISION", "cylinder", 0.4, 0.0),
            Device("VISION_PUSH_X", "VISION", "cylinder", 0.4, 0.0),
            Device("VISION_PUSH_Y", "VISION", "cylinder", 0.4, 0.0),
            Device("DISP_LIFT", "DISPENSER", "cylinder", 0.4, 0.0),
            Device("DISP_FIXTURE_VAC", "DISPENSER", "vacuum", 0.3, 0.0),
            Device("NG_PICK_Z", "OUTFEED", "cylinder", 0.3, 0.0),
            Device("NG_PICK_VAC", "OUTFEED", "vacuum", 0.2, 0.0),
        ]
        devices += [Device(f"{s}_BELT", s, "belt", 0.0, 0.0) for s in stations]
        self.devices = {d.id: d for d in devices}
        for d in devices:
            d.position = d.target = d.auto_ready
        axes = [
            Axis("DISP_X", "DISPENSER", -80, 180, 200, 0.0, {"HOME": 0.0, "WORK_START": -58.0, "SCALE": SCALE_XY[0]}),
            Axis("DISP_Y", "DISPENSER", -220, 40, 200, 0.0, {"HOME": 0.0, "WORK_START": -24.0, "SCALE": SCALE_XY[1]}),
            Axis("DISP_Z", "DISPENSER", -12, 100, 60, 88.0, {"SAFE": 88.0, "WORK": 0.0, "SCALE_SHOT": -10.0}),
            Axis("SCAN_X", "INSPECTION", -84, 84, 150, -84.0, {"HOME": -84.0, "END": 84.0}),
            Axis("NG_PICK_Y", "OUTFEED", 0, 260, 300, 0.0, {"HOME": 0.0, "NG_BUFFER": 260.0}),
        ]
        self.axes = {a.id: a for a in axes}
        self._homing = False

    # ---- commands -------------------------------------------------------------

    def set_device(self, device_id: str, on: bool, by: str) -> None:
        d = self._device(device_id)
        self._check_device(d, on)
        d.command(on)
        self.m.log.event("INFO", d.unit, "Manual command", device=d.id, cmd="ON" if on else "OFF", by=by)

    def move_axis(self, axis_id: str, mm: float, by: str) -> None:
        a = self._axis(axis_id)
        self._check_axis(a, mm)
        a.move_to(round(mm, 3))
        self.m.log.event("INFO", a.unit, "Manual move", axis=a.id, target=f"{mm:.2f}mm", by=by)

    def jog_axis(self, axis_id: str, delta_mm: float, by: str) -> None:
        a = self._axis(axis_id)
        self.move_axis(axis_id, min(a.max_mm, max(a.min_mm, a.target + delta_mm)), by)

    def home_all(self, by: str) -> None:
        """Bring everything to its AUTO-ready position, in stages so nothing collides."""
        self.m.log.event("INFO", "MACHINE", "Manual return to auto position", by=by)
        self._homing = True

    def not_ready_for_auto(self) -> list[str]:
        problems = [d.id for d in self.devices.values() if d.position != d.auto_ready or d.moving]
        problems += [a.id for a in self.axes.values() if a.position != a.home_mm or a.moving]
        return problems

    def sync_from_auto(self) -> None:
        """Entering MANUAL: start from where the stopped sequences left the hardware."""
        st = {s.name: s for s in self.m.stations}
        for d in self.devices.values():
            d.position = d.target = d.auto_ready

        def lift_up(name: str) -> bool:
            return st[name].step in STEPS_LIFT_UP[name] or st[name].step == "LIFT_DOWN"

        self.devices["VISION_LIFT"].position = self.devices["VISION_LIFT"].target = 1.0 if lift_up("VISION") else 0.0
        pushed = 1.0 if st["VISION"].step in {"PUSH_ALIGN", "SETTLE", "CAPTURE", "PROCESS"} else 0.0
        for pid in ("VISION_PUSH_X", "VISION_PUSH_Y"):
            self.devices[pid].position = self.devices[pid].target = pushed
        self.devices["DISP_LIFT"].position = self.devices["DISP_LIFT"].target = 1.0 if lift_up("DISPENSER") else 0.0
        vac = 1.0 if self.m.dispenser.vacuum_on else 0.0
        self.devices["DISP_FIXTURE_VAC"].position = self.devices["DISP_FIXTURE_VAC"].target = vac
        for a in self.axes.values():
            a.position = a.target = a.home_mm
        if st["DISPENSER"].step in {"HEIGHT_MEASURE", "DISPENSE", "DWELL"}:
            self.axes["DISP_X"].position = self.axes["DISP_X"].target = -58.0
            self.axes["DISP_Y"].position = self.axes["DISP_Y"].target = -24.0
            self.axes["DISP_Z"].position = self.axes["DISP_Z"].target = 0.0

    # ---- simulation -------------------------------------------------------------

    def update(self, dt: float) -> None:
        slowdown = self.m.physics.cylinder_slowdown()
        for d in self.devices.values():
            arrived = d.update(dt, slowdown)
            if arrived is not None and d.kind != "belt":
                state = "ON" if d.position >= 1 else "OFF"
                self.m.log.event("INFO", d.unit, "Manual done", device=d.id, state=state, t=f"{arrived:.3f}s")
        for a in self.axes.values():
            if a.update(dt):
                self.m.log.event("INFO", a.unit, "Manual move done", axis=a.id, position=f"{a.position:.2f}mm")
        if self._homing:
            self._continue_home()

    def _continue_home(self) -> None:
        dev, ax = self.devices, self.axes

        def ensure(device_id: str, on: bool) -> None:
            if dev[device_id].target != (1.0 if on else 0.0):
                dev[device_id].command(on)

        def send_home(axis_id: str) -> None:
            if ax[axis_id].target != ax[axis_id].home_mm:
                ax[axis_id].move_to(ax[axis_id].home_mm)

        # Stage 1: always safe - retract, release, stop belts, raise the needle and the picker.
        for d in dev.values():
            if d.kind in ("vacuum", "belt") or d.id in ("VISION_PUSH_X", "VISION_PUSH_Y", "NG_PICK_Z"):
                ensure(d.id, False)
            elif d.id.endswith("_STOPPER"):
                ensure(d.id, True)
        send_home("DISP_Z")
        send_home("SCAN_X")
        # Stage 2: only once what could collide is clear.
        if dev["VISION_PUSH_X"].position == 0 and dev["VISION_PUSH_Y"].position == 0:
            ensure("VISION_LIFT", False)
        if not ax["DISP_Z"].moving and ax["DISP_Z"].position >= SAFE_Z_MM:
            ensure("DISP_LIFT", False)
            send_home("DISP_X")
            send_home("DISP_Y")
        if dev["NG_PICK_Z"].position == 0:
            send_home("NG_PICK_Y")
        if not self.not_ready_for_auto():
            self._homing = False
            self.m.log.event("INFO", "MACHINE", "All devices at auto position")

    def vacuum_kpa(self, device_id: str) -> float:
        """What the vacuum switch reads: it only builds up when a part seals the pads."""
        d = self.devices[device_id]
        if d.position < 1:
            return 0.0
        if device_id == "DISP_FIXTURE_VAC":
            seated = self.m.dispenser.wp is not None and self.devices["DISP_LIFT"].position >= 1
            return self.m.physics.fixture.achievable_vacuum_kpa if seated else -4.0
        picked = self.m.outfeed.wp is not None and self.devices["NG_PICK_Z"].position >= 1
        return -78.0 if picked else -4.0

    def view(self) -> dict:
        return {
            "devices": [{**d.view(), **({"kpa": round(self.vacuum_kpa(d.id), 1)} if d.kind == "vacuum" else {})}
                        for d in self.devices.values()],
            "axes": [a.view() for a in self.axes.values()],
        }

    # ---- interlocks -------------------------------------------------------------

    def _check_device(self, d: Device, on: bool) -> None:
        dev = self.devices
        if d.id in ("VISION_PUSH_X", "VISION_PUSH_Y") and on and dev["VISION_LIFT"].position < 1:
            raise InterlockError("비전 리프트가 올라가 있지 않아 푸셔를 전진할 수 없습니다")
        if d.id == "VISION_LIFT" and not on and (dev["VISION_PUSH_X"].position > 0 or dev["VISION_PUSH_Y"].position > 0):
            raise InterlockError("푸셔가 전진해 있어 비전 리프트를 내릴 수 없습니다")
        if d.id == "DISP_LIFT" and not on and self.axes["DISP_Z"].position < LOW_Z_MM:
            raise InterlockError("니들이 낮은 위치에 있어 디스펜서 리프트를 내릴 수 없습니다 (Z를 먼저 올리세요)")
        if d.id == "NG_PICK_Z" and on:
            y = self.axes["NG_PICK_Y"]
            if y.moving or y.position not in (0.0, 260.0):
                raise InterlockError("NG 픽커 Y축이 원점이나 NG 버퍼 위치에 있을 때만 내릴 수 있습니다")
        if d.kind == "belt" and on:
            lift = {"VISION": "VISION_LIFT", "DISPENSER": "DISP_LIFT"}.get(d.unit)
            if lift and dev[lift].position > 0:
                raise InterlockError("리프트가 올라가 있어 이 구간 벨트를 돌릴 수 없습니다")

    def _check_axis(self, a: Axis, mm: float) -> None:
        z = self.axes["DISP_Z"]
        if a.id in ("DISP_X", "DISP_Y") and (z.position < SAFE_Z_MM or z.moving):
            raise InterlockError(f"Z축이 안전 높이({SAFE_Z_MM:g} mm) 위에 있을 때만 X/Y를 움직일 수 있습니다")
        if a.id == "DISP_Z" and mm < LOW_Z_MM:
            x, y = self.axes["DISP_X"], self.axes["DISP_Y"]
            at_scale = abs(x.position - SCALE_XY[0]) < 5 and abs(y.position - SCALE_XY[1]) < 5
            over_part = abs(x.position) <= 75 and abs(y.position) <= 40
            if at_scale:
                return
            if not over_part:
                raise InterlockError("니들은 제품 위나 저울 위에서만 낮출 수 있습니다")
            if self.devices["DISP_LIFT"].position < 1:
                raise InterlockError("디스펜서 리프트가 올라가 있을 때만 니들을 낮출 수 있습니다")
            if mm < 0:
                raise InterlockError("제품 위에서는 0 mm(도포 높이) 아래로 내릴 수 없습니다")
        if a.id == "NG_PICK_Y" and self.devices["NG_PICK_Z"].position > 0:
            raise InterlockError("NG 픽커가 내려가 있어 Y축을 움직일 수 없습니다")

    def _device(self, device_id: str) -> Device:
        if device_id not in self.devices:
            raise InterlockError(f"알 수 없는 장치: {device_id}")
        return self.devices[device_id]

    def _axis(self, axis_id: str) -> Axis:
        if axis_id not in self.axes:
            raise InterlockError(f"알 수 없는 축: {axis_id}")
        return self.axes[axis_id]
