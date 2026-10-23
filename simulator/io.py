"""PLC-style I/O map: input (X) and output (Y) bits derived from the machine state.

In AUTO the bits follow the station sequences (a lift's up-solenoid turns on at LIFT_UP and its
up-sensor once the stroke is done). In MANUAL they follow the manual devices. Every change is
written to io_trace.csv, like a PLC data logger.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from simulator.machine import Machine

VISION_LIFT_UP = {"PUSH_ALIGN", "SETTLE", "CAPTURE", "PROCESS", "RELEASE"}
VISION_PUSHED = {"SETTLE", "CAPTURE", "PROCESS"}
DISP_LIFT_UP = {"VACUUM_ON", "APPROACH", "HEIGHT_MEASURE", "DISPENSE", "DWELL", "RETRACT", "VACUUM_OFF"}
DISP_AXES_MOVING = {"APPROACH", "DISPENSE", "RETRACT", "MOVE_TO_SCALE", "WEIGH", "MOVE_FROM_SCALE"}
STATIONS = ["INFEED", "VISION", "DISPENSER", "INSPECTION", "OUTFEED"]
UNIT_KO = {"INFEED": "투입", "VISION": "비전", "DISPENSER": "디스펜서", "INSPECTION": "검사", "OUTFEED": "배출"}


@dataclass
class Signal:
    address: str
    id: str
    label: str
    unit: str
    read: Callable[[], bool]
    device: str | None = None  # manual device an output can force
    invert: bool = False       # output ON means the device goes to its home position


class IoMonitor:
    def __init__(self, machine: Machine):
        self.m = machine
        self.inputs: list[Signal] = []
        self.outputs: list[Signal] = []
        self._define()
        self.values: dict[str, bool] = {}
        self.changed_at: dict[str, str] = {}
        self.dirty = True

    # ---- evaluation -------------------------------------------------------------

    def update(self, force: bool = False) -> None:
        """Re-read every bit if something may have changed; log the bits that did."""
        if not (self.dirty or force):
            return
        self.dirty = False
        ts = self.m.log.timestamp()
        for sig in self.inputs + self.outputs:
            value = bool(sig.read())
            if self.values.get(sig.address) != value:
                if sig.address in self.values:  # skip the initial read
                    self.m.log.io(ts, sig.address, sig.id, value)
                self.values[sig.address] = value
                self.changed_at[sig.address] = ts

    def view(self) -> dict:
        def rows(signals: list[Signal]) -> list[dict]:
            return [{
                "address": s.address, "id": s.id, "label": s.label, "unit": s.unit,
                "value": self.values.get(s.address, False), "changed_at": self.changed_at.get(s.address),
                "device": s.device, "invert": s.invert,
            } for s in signals]
        return {"inputs": rows(self.inputs), "outputs": rows(self.outputs)}

    def io_map(self) -> list[dict]:
        """Static address list for machine_info.json."""
        return [{"address": s.address, "id": s.id, "label": s.label, "unit": s.unit}
                for s in self.inputs + self.outputs]

    # ---- state helpers ----------------------------------------------------------

    def _st(self, name: str):
        return next(s for s in self.m.stations if s.name == name)

    def _step(self, name: str) -> str:
        return self._st(name).step

    def _manual(self, device_id: str):
        return self.m.manual.devices[device_id] if self.m.op_mode == "MANUAL" else None

    def _cylinder(self, device_id: str, out_steps: set[str], work_steps: set[str], station: str,
                  moving_steps: set[str]) -> tuple[Callable[[], bool], Callable[[], bool], Callable[[], bool]]:
        """(solenoid, home sensor, work sensor) readers for a cylinder."""
        def out() -> bool:
            d = self._manual(device_id)
            return d.target >= 1 if d else self._step(station) in out_steps

        def work() -> bool:
            d = self._manual(device_id)
            return d.position >= 0.98 if d else self._step(station) in work_steps

        def home() -> bool:
            d = self._manual(device_id)
            if d:
                return d.position <= 0.02
            step = self._step(station)
            return step not in out_steps and step not in moving_steps

        return out, home, work

    def _receiving(self, name: str | None) -> bool:
        return name is not None and self._step(name) == "TRANSFER_IN"

    def _stopper_down(self, i: int) -> Callable[[], bool]:
        name = STATIONS[i]
        nxt = STATIONS[i + 1] if i + 1 < len(STATIONS) else None

        def read() -> bool:
            d = self._manual(f"{name}_STOPPER")
            if d:
                return d.target < 1
            if name == "OUTFEED":
                return self._step(name) in ("STOPPER_DOWN", "TRANSFER_OUT")
            return self._receiving(nxt)
        return read

    def _belt(self, i: int) -> Callable[[], bool]:
        name = STATIONS[i]
        nxt = STATIONS[i + 1] if i + 1 < len(STATIONS) else None

        def read() -> bool:
            d = self._manual(f"{name}_BELT")
            if d:
                return d.position >= 1
            running = self.m.mode.value == "RUNNING"
            out = name == "OUTFEED" and self._step(name) == "TRANSFER_OUT"
            return running and (self._receiving(name) or self._receiving(nxt) or out)
        return read

    def _present(self, name: str) -> Callable[[], bool]:
        return lambda: self._st(name).wp is not None and self._step(name) != "TRANSFER_IN"

    def _inpos(self, axis_id: str, station: str, moving_steps: set[str]) -> Callable[[], bool]:
        def read() -> bool:
            if self.m.op_mode == "MANUAL":
                return not self.m.manual.axes[axis_id].moving
            return self._step(station) not in moving_steps
        return read

    def _vacuum_switch(self, device_id: str) -> Callable[[], bool]:
        def read() -> bool:
            if self.m.op_mode == "MANUAL":
                return self.m.manual.vacuum_kpa(device_id) <= -60
            if device_id == "DISP_FIXTURE_VAC":
                return self.m.dispenser.vacuum_on and self._step("DISPENSER") != "VACUUM_ON"
            return self.m.outfeed.picker_vacuum and self._step("OUTFEED") != "VACUUM_ON"
        return read

    def _vacuum_out(self, device_id: str, auto: Callable[[], bool]) -> Callable[[], bool]:
        def read() -> bool:
            d = self._manual(device_id)
            return d.target >= 1 if d else auto()
        return read

    # ---- the map ----------------------------------------------------------------

    def _define(self) -> None:
        m = self.m
        x: list[tuple] = []
        y: list[tuple] = []

        # machine-wide
        x += [
            ("ESTOP_OK", "비상정지 해제 (정상)", "MACHINE", lambda: not m.estop),
            ("DOOR_FL_CLOSED", "전면 좌측 도어 닫힘", "MACHINE", lambda: not m.doors_open["FRONT_LEFT"]),
            ("DOOR_FR_CLOSED", "전면 우측 도어 닫힘", "MACHINE", lambda: not m.doors_open["FRONT_RIGHT"]),
            ("MAIN_AIR_OK", "메인 에어 압력 스위치", "MACHINE",
             lambda: m.physics.air.supply_kpa >= m.cfg["air_pressure_switch_kpa"]),
            ("UPSTREAM_PART_AVAILABLE", "이전 공정 제품 있음 (SMEMA)", "INFEED",
             lambda: self._step("INFEED") != "WAIT_UPSTREAM"),
            ("DOWNSTREAM_READY", "다음 공정 받을 준비 (SMEMA)", "OUTFEED",
             lambda: self._step("OUTFEED") != "WAIT_DOWNSTREAM"),
        ]
        y += [
            ("TOWER_GREEN", "시그널 타워 녹색", "MACHINE", lambda: m.mode.value == "RUNNING"),
            ("TOWER_YELLOW", "시그널 타워 황색", "MACHINE", lambda: m.mode.value == "STOPPED"),
            ("TOWER_RED", "시그널 타워 적색", "MACHINE", lambda: m.mode.value == "ALARM"),
            ("BUZZER", "부저", "MACHINE", lambda: m.mode.value == "ALARM"),
            ("MACHINE_READY", "투입 가능 → 이전 공정 (SMEMA)", "INFEED",
             lambda: self._step("INFEED") in ("WAIT_UPSTREAM", "TRANSFER_IN")),
            ("PART_AVAILABLE", "제품 있음 → 다음 공정 (SMEMA)", "OUTFEED",
             lambda: self._step("OUTFEED") in ("WAIT_DOWNSTREAM", "STOPPER_DOWN", "TRANSFER_OUT")),
        ]

        # per conveyor zone: part sensor, stopper, belt motor
        for i, name in enumerate(STATIONS):
            ko = UNIT_KO[name]
            down = self._stopper_down(i)
            x += [
                (f"{name}_PART_SNS", f"{ko} 제품 감지", name, self._present(name)),
                (f"{name}_STOPPER_UP_SNS", f"{ko} 스토퍼 상승 센서", name, lambda down=down: not down()),
            ]
            y += [
                (f"{name}_BELT_MOTOR", f"{ko} 컨베이어 모터", name, self._belt(i), f"{name}_BELT", False),
                (f"{name}_STOPPER_DOWN_SOL", f"{ko} 스토퍼 하강 솔레노이드", name, down, f"{name}_STOPPER", True),
            ]

        # infeed
        y += [("ID_READER_TRIG", "2D 코드 리더 트리거", "INFEED", lambda: self._step("INFEED") == "ID_READ")]

        # vision
        lift = self._cylinder("VISION_LIFT", {"LIFT_UP"} | VISION_LIFT_UP, VISION_LIFT_UP, "VISION", {"LIFT_DOWN"})
        push_x = self._cylinder("VISION_PUSH_X", {"PUSH_ALIGN"} | VISION_PUSHED, VISION_PUSHED, "VISION", {"RELEASE"})
        push_y = self._cylinder("VISION_PUSH_Y", {"PUSH_ALIGN"} | VISION_PUSHED, VISION_PUSHED, "VISION", {"RELEASE"})
        x += [
            ("VISION_LIFT_DOWN_SNS", "비전 리프트 하강 센서", "VISION", lift[1]),
            ("VISION_LIFT_UP_SNS", "비전 리프트 상승 센서", "VISION", lift[2]),
            ("VISION_PUSH_X_BACK_SNS", "푸셔 X 후진 센서", "VISION", push_x[1]),
            ("VISION_PUSH_X_FWD_SNS", "푸셔 X 전진 센서", "VISION", push_x[2]),
            ("VISION_PUSH_Y_BACK_SNS", "푸셔 Y 후진 센서", "VISION", push_y[1]),
            ("VISION_PUSH_Y_FWD_SNS", "푸셔 Y 전진 센서", "VISION", push_y[2]),
        ]
        y += [
            ("VISION_LIFT_UP_SOL", "비전 리프트 상승 솔레노이드", "VISION", lift[0], "VISION_LIFT", False),
            ("VISION_PUSH_X_SOL", "푸셔 X 전진 솔레노이드", "VISION", push_x[0], "VISION_PUSH_X", False),
            ("VISION_PUSH_Y_SOL", "푸셔 Y 전진 솔레노이드", "VISION", push_y[0], "VISION_PUSH_Y", False),
            ("RING_LIGHT", "링 조명", "VISION", lambda: self._step("VISION") == "CAPTURE"),
            ("CAMERA_TRIG", "카메라 트리거", "VISION", lambda: self._step("VISION") == "CAPTURE"),
        ]

        # dispenser
        d_lift = self._cylinder("DISP_LIFT", {"LIFT_UP"} | DISP_LIFT_UP, DISP_LIFT_UP, "DISPENSER", {"LIFT_DOWN", "RESEAT"})
        x += [
            ("DISP_LIFT_DOWN_SNS", "디스펜서 리프트 하강 센서", "DISPENSER", d_lift[1]),
            ("DISP_LIFT_UP_SNS", "디스펜서 리프트 상승 센서", "DISPENSER", d_lift[2]),
            ("FIXTURE_VAC_SW", "지그 진공 스위치", "DISPENSER", self._vacuum_switch("DISP_FIXTURE_VAC")),
            ("DISP_X_INPOS", "디스펜서 X축 INPOS", "DISPENSER", self._inpos("DISP_X", "DISPENSER", DISP_AXES_MOVING)),
            ("DISP_Y_INPOS", "디스펜서 Y축 INPOS", "DISPENSER", self._inpos("DISP_Y", "DISPENSER", DISP_AXES_MOVING)),
            ("DISP_Z_INPOS", "디스펜서 Z축 INPOS", "DISPENSER", self._inpos("DISP_Z", "DISPENSER", DISP_AXES_MOVING)),
        ]
        y += [
            ("DISP_LIFT_UP_SOL", "디스펜서 리프트 상승 솔레노이드", "DISPENSER", d_lift[0], "DISP_LIFT", False),
            ("FIXTURE_VAC_SOL", "지그 진공 솔레노이드", "DISPENSER",
             self._vacuum_out("DISP_FIXTURE_VAC", lambda: m.dispenser.vacuum_on), "DISP_FIXTURE_VAC", False),
            ("DISPENSE_VALVE", "토출 밸브 (디스펜서 컨트롤러 신호)", "DISPENSER", lambda: m.dispenser.valve_open),
            ("HEIGHT_LASER", "높이 측정 레이저", "DISPENSER", lambda: self._step("DISPENSER") == "HEIGHT_MEASURE"),
        ]

        # inspection
        x += [("SCAN_X_INPOS", "스캔 축 INPOS", "INSPECTION",
               self._inpos("SCAN_X", "INSPECTION", {"SCAN", "SCAN_RETURN"}))]
        y += [("LINE_LASER", "라인 레이저", "INSPECTION", lambda: self._step("INSPECTION") == "SCAN")]

        # outfeed NG picker
        pick = self._cylinder("NG_PICK_Z", {"PICK_DOWN", "VACUUM_ON", "PLACE"}, {"VACUUM_ON"}, "OUTFEED",
                              {"PICK_UP"})
        x += [
            ("NG_PICK_UP_SNS", "NG 픽커 상승 센서", "OUTFEED", pick[1]),
            ("NG_PICK_DOWN_SNS", "NG 픽커 하강 센서", "OUTFEED", pick[2]),
            ("NG_PICK_VAC_SW", "NG 픽커 진공 스위치", "OUTFEED", self._vacuum_switch("NG_PICK_VAC")),
            ("NG_PICK_Y_INPOS", "NG 픽커 Y축 INPOS", "OUTFEED",
             self._inpos("NG_PICK_Y", "OUTFEED", {"MOVE_TO_NG", "RETURN"})),
        ]
        y += [
            ("NG_PICK_DOWN_SOL", "NG 픽커 하강 솔레노이드", "OUTFEED", pick[0], "NG_PICK_Z", False),
            ("NG_PICK_VAC_SOL", "NG 픽커 진공 솔레노이드", "OUTFEED",
             self._vacuum_out("NG_PICK_VAC", lambda: m.outfeed.picker_vacuum), "NG_PICK_VAC", False),
        ]

        # PLC-style octal addresses: X000..X007, X010.. / Y000..
        self.inputs = [Signal(f"X{i:03o}", sid, label, unit, read) for i, (sid, label, unit, read) in enumerate(x)]
        self.outputs = [
            Signal(f"Y{i:03o}", row[0], row[1], row[2], row[3], *(row[4:6] if len(row) > 4 else ()))
            for i, row in enumerate(y)
        ]
