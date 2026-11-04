"""Who is logged in at the HMI and what they may do.

The real machine has one panel, so there is one session. Permissions are checked here on
the server; the HMI only greys out what the current level cannot use.
"""
from __future__ import annotations

import time
from pathlib import Path
import json

LEVELS = ["GUEST", "OPERATOR", "ENGINEER", "MAKER"]

# Minimum level per HMI action. Stopping is always allowed, for safety.
REQUIRED = {
    "stop": "GUEST",
    "cycle_stop": "GUEST",
    "start": "OPERATOR",
    "reset": "OPERATOR",
    "initialize": "OPERATOR",
    "maintenance": "OPERATOR",
    "op_mode": "ENGINEER",
    "manual": "ENGINEER",
    "io_force": "ENGINEER",
    "recipe_load": "ENGINEER",
    "recipe_edit": "MAKER",
    "run_mode": "ENGINEER",
    "counter_reset": "ENGINEER",
    "settings": "ENGINEER",   # opening the settings for change; each value also has its own level
}
AUTO_LOGOUT_MIN = (1, 60)       # range for the auto logout setting (minutes)
# Maintenance actions that need more than an operator.
MAINTENANCE_LEVEL = {"needle_calibration": "ENGINEER", "replace_vacuum_pad": "ENGINEER"}


class AccessDenied(Exception):
    pass


class HmiSession:
    def __init__(self, config_path: Path):
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        self.users = {u["id"]: u for u in cfg["users"]}
        self.auto_logout_s = cfg["auto_logout_min"] * 60.0
        self.user: dict | None = None
        self._last_activity = 0.0

    @property
    def level(self) -> str:
        self._check_timeout()
        return self.user["level"] if self.user else "GUEST"

    @property
    def by(self) -> str:
        """Name written into log lines for commands from the panel."""
        return self.user["id"] if self.user else "HMI"

    def login(self, user_id: str, pin: str) -> dict:
        user = self.users.get(user_id)
        if user is None or user["pin"] != pin:
            raise AccessDenied("사용자 ID 또는 PIN이 맞지 않습니다")
        self.user = user
        self.touch()
        return user

    def logout(self) -> None:
        self.user = None

    def touch(self) -> None:
        self._last_activity = time.monotonic()

    def allowed(self, action: str, detail: str = "") -> bool:
        need = MAINTENANCE_LEVEL.get(detail, REQUIRED[action]) if action == "maintenance" else REQUIRED[action]
        return LEVELS.index(self.level) >= LEVELS.index(need)

    def require(self, action: str, detail: str = "") -> None:
        if not self.allowed(action, detail):
            need = MAINTENANCE_LEVEL.get(detail, REQUIRED[action]) if action == "maintenance" else REQUIRED[action]
            raise AccessDenied(f"권한이 없습니다: {need} 이상 필요 (현재 {self.level})")
        self.touch()

    def require_level(self, need: str, what: str) -> None:
        """For settings whose level is per value rather than per command."""
        if LEVELS.index(self.level) < LEVELS.index(need):
            raise AccessDenied(f"권한이 없습니다: {what}은(는) {need} 이상 필요 (현재 {self.level})")
        self.touch()

    @property
    def auto_logout_min(self) -> float:
        return self.auto_logout_s / 60.0

    def set_auto_logout_min(self, minutes: float) -> None:
        lo, hi = AUTO_LOGOUT_MIN
        if not lo <= minutes <= hi:
            raise ValueError(f"자동 로그아웃: {lo}~{hi}분 범위여야 합니다 (입력 {minutes:g})")
        self.auto_logout_s = minutes * 60.0

    def view(self) -> dict:
        level = self.level
        return {
            "user": {"id": self.user["id"], "name": self.user["name"]} if self.user else None,
            "level": level,
            "permissions": {a: self.allowed(a) for a in REQUIRED},
            "users": [{"id": u["id"], "name": u["name"], "level": u["level"]} for u in self.users.values()],
            "maintenance_level": MAINTENANCE_LEVEL,
            "auto_logout_min": round(self.auto_logout_min),
        }

    def _check_timeout(self) -> None:
        if self.user and time.monotonic() - self._last_activity > self.auto_logout_s:
            self.user = None
