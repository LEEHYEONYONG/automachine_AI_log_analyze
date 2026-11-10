"""사건 그래프 묶기. DB 없이 돈다."""
import unittest
from datetime import datetime, timedelta

from app import trend

T0 = datetime(2026, 11, 4, 10, 0, 0)
PROFILE = {"A": {"disp_pressure_kpa": {"mean": 240.0, "std": 0.5}, "vacuum_kpa": {"mean": -85.0, "std": 0.2}}}


def sample(sec, pressure, vacuum, valve=1, mode="RUNNING"):
    return {"ts": T0 + timedelta(seconds=sec), "mode": mode, "disp_valve_open": valve,
            "disp_pressure_kpa": pressure, "fixture_vac_kpa": vacuum}


class Trend(unittest.TestCase):
    def test_window_is_an_hour_before_and_twenty_minutes_after(self):
        start, end = trend.window(T0, T0 + timedelta(minutes=5))
        self.assertEqual(start, T0 - timedelta(minutes=60))
        self.assertEqual(end, T0 + timedelta(minutes=25))

    def test_long_incidents_keep_the_first_alert(self):
        start, end = trend.window(T0, T0 + timedelta(hours=20))
        self.assertEqual(end - start, trend.MAX_SPAN)

    def test_uses_only_dispensing_samples_like_the_rules(self):
        samples = [sample(1, 240.0, -85.0), sample(2, 100.0, 0.0, valve=0), sample(3, 50.0, 0.0, mode="STOPPED"),
                   sample(4, 242.0, -84.0)]
        out = trend.build(samples, [{"start_time": T0, "recipe": "A"}], T0, T0 + timedelta(seconds=40), PROFILE)
        self.assertEqual(out["step_s"], trend.MIN_STEP_S)
        [p] = out["points"]
        self.assertEqual((p["pressure"], p["vacuum"]), (241.0, -84.5))     # 토출 중 두 샘플의 중앙값
        self.assertEqual(p["pressure_band"], [238.5, 241.5])               # 평균 ± 3σ
        self.assertEqual(p["recipe"], "A")

    def test_unknown_recipe_has_no_band_and_buckets_stay_under_the_cap(self):
        end = T0 + timedelta(hours=8)
        samples = [sample(s, 240.0, -85.0) for s in range(0, 8 * 3600, 30)]
        out = trend.build(samples, [{"start_time": T0, "recipe": "B"}], T0, end, PROFILE)
        self.assertLessEqual(len(out["points"]), trend.MAX_POINTS)
        self.assertIsNone(out["points"][0]["vacuum_band"])


if __name__ == "__main__":
    unittest.main()
