from dataclasses import dataclass, field
from datetime import datetime

PRODUCTION_FIELDS = [
    "wp_id", "lot_id", "recipe", "start_time", "end_time", "cycle_s",
    "align_dx_mm", "align_dy_mm", "align_score",
    "fixture_vac_kpa", "vac_retries", "disp_pressure_kpa", "disp_temp_c", "nozzle_height_mm",
    "bead_width_mm", "bead_offset_mm", "judge", "ng_reason",
]


@dataclass
class Workpiece:
    wp_id: str
    lot_id: str
    recipe: str
    started_at: datetime
    data: dict = field(default_factory=dict)    # values the machine measured and records
    hidden: dict = field(default_factory=dict)  # physical truth (e.g. real bead weight); never logged
    judge: str = ""
    ng_reason: str = ""

    def production_row(self, ended_at: datetime) -> dict:
        return {
            "wp_id": self.wp_id,
            "lot_id": self.lot_id,
            "recipe": self.recipe,
            "start_time": self.started_at,
            "end_time": ended_at,
            "cycle_s": round((ended_at - self.started_at).total_seconds(), 1),
            **self.data,
            "judge": self.judge,
            "ng_reason": self.ng_reason,
        }
