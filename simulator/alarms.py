from dataclasses import dataclass


@dataclass(frozen=True)
class AlarmDef:
    code: str
    unit: str
    text: str
    on_reset: str  # "retry": rerun the step, "scrap": remove the part as NG, "continue": part already done


ALARMS = {a.code: a for a in [
    AlarmDef("E1001", "LOADER", "Pick vacuum not reached (retry exceeded)", "retry"),
    AlarmDef("E1002", "LOADER", "Input magazine empty", "retry"),
    AlarmDef("E2001", "VISION", "Align mark not found", "scrap"),
    AlarmDef("E2002", "VISION", "Align offset out of range", "scrap"),
    AlarmDef("E3002", "DISPENSER", "Syringe temperature out of range", "retry"),
    AlarmDef("E3003", "DISPENSER", "Syringe level low", "retry"),
    AlarmDef("E3005", "DISPENSER", "Weight check out of spec", "retry"),
    AlarmDef("E3006", "DISPENSER", "Material pot life expired", "retry"),
    AlarmDef("E4001", "INSPECTION", "Consecutive bead NG", "continue"),
    AlarmDef("E5001", "UNLOADER", "Output tray full", "retry"),
    AlarmDef("E9001", "MACHINE", "Main air pressure low", "retry"),
]}


class MachineAlarm(Exception):
    def __init__(self, code: str, detail: str = "", reason: str = ""):
        super().__init__(f"{code} {detail}".strip())
        self.code = code
        self.detail = detail
        self.reason = reason  # e.g. the NG type behind E4001, which the operator looks at
