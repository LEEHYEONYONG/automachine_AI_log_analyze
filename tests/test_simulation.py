import csv
import json
import tempfile
import unittest
from pathlib import Path

from simulator.simulation import Simulation

ROOT = Path(__file__).resolve().parent.parent
MACHINE_CFG = json.loads((ROOT / "config" / "machine.json").read_text(encoding="utf-8"))


def scenario(name="test", faults=(), seed=1, start="2026-10-19T08:00:00", schedule=()):
    return {"name": name, "start_time": start, "seed": seed, "faults": list(faults), "schedule": list(schedule)}


def production(sim):
    with open(sim.log_dir / "production.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(scn, hours):
    tmp = tempfile.TemporaryDirectory()
    sim = Simulation(MACHINE_CFG, scn, Path(tmp.name))
    summary = sim.run(hours)
    truth = json.loads((sim.truth_dir / "faults.json").read_text(encoding="utf-8"))
    return tmp, sim, summary, truth


class SimulationTest(unittest.TestCase):
    def test_same_seed_gives_identical_logs(self):
        logs = []
        for _ in range(2):
            tmp, sim, _, _ = run(scenario(), hours=0.25)
            with tmp:
                logs.append((sim.log_dir / "event.log").read_bytes())
        self.assertEqual(logs[0], logs[1])

    def test_normal_run_produces_parts(self):
        tmp, sim, summary, truth = run(scenario(), hours=1)
        with tmp:
            self.assertGreater(summary["parts"], 400)
            self.assertGreater(summary["yield_pct"], 95)
            self.assertEqual(truth["faults"], [])

    def test_logs_do_not_reveal_the_fault(self):
        faults = [
            {"type": "nozzle_clog", "start_after_min": 5, "params": {"ramp_min": 20}},
            {"type": "air_bubble", "start_after_min": 5},
            {"type": "needle_tip_buildup", "start_after_min": 5},
            {"type": "needle_offset", "start_after_min": 5},
            {"type": "air_supply_drop", "start_after_min": 5},
            {"type": "recipe_pressure_error", "start_after_min": 5},
        ]
        tmp, sim, _, _ = run(scenario("mixed", faults), hours=0.5)
        with tmp:
            self.assertNotIn("clog", sim.run_id)
            for path in sim.log_dir.iterdir():
                text = path.read_text(encoding="utf-8").lower()
                for word in ("clog", "bubble", "buildup", "needle_offset", "air_supply", "recipe_pressure_error"):
                    self.assertNotIn(word, text, f"{word} in {path.name}")

    def test_air_supply_drop_hits_dispenser_and_loader_then_recovers(self):
        drop = {"type": "air_supply_drop", "start_after_min": 2,
                "params": {"min_supply_kpa": 330, "ramp_min": 1, "hold_min": 10}}
        tmp = tempfile.TemporaryDirectory()
        with tmp:
            sim = Simulation(MACHINE_CFG, scenario("air", [drop]), Path(tmp.name))
            try:
                sim.operator.start_shift()
                for _ in range(round(8 * 60 / sim.clock.dt)):  # into the hold phase
                    sim.step()
                p = sim.machine.physics
                # 330 kPa supply -> ~210 kPa regulator output (plant air also wanders by ~±12 kPa)
                self.assertLess(p.dispenser.regulator_out_kpa, 235)
                self.assertGreater(p.loader.achievable_vacuum_kpa, -68)
                for _ in range(round(10 * 60 / sim.clock.dt)):
                    sim.step()
                fault = sim.faults.faults[0]
                self.assertEqual(fault.resolved_action, "self: plant air recovered")
                self.assertGreater(p.dispenser.regulator_out_kpa, 249)
            finally:
                sim.close()

    def test_model_change_switches_recipe_and_lot(self):
        change = {"type": "model_change", "at_min": 20, "recipe": "REAR_HOUSING_ADH_B"}
        tmp, sim, _, _ = run(scenario(schedule=[change]), hours=1.5)
        with tmp:
            rows = production(sim)
            self.assertEqual(rows[0]["recipe"], "REAR_HOUSING_ADH_A")
            self.assertEqual(rows[-1]["recipe"], "REAR_HOUSING_ADH_B")
            self.assertNotEqual(rows[0]["lot_id"], rows[-1]["lot_id"])
            self.assertIn("Model change start", (sim.log_dir / "event.log").read_text(encoding="utf-8"))

    def test_break_stops_the_line(self):
        tmp, sim, _, _ = run(scenario(start="2026-10-19T09:50:00"), hours=0.5)
        with tmp:
            events = (sim.log_dir / "event.log").read_text(encoding="utf-8")
            self.assertIn("Break start", events)
            self.assertIn("Cycle stop requested reason=break", events)
            during_break = [r for r in production(sim) if "10:02" <= r["end_time"][11:16] < "10:10"]
            self.assertEqual(during_break, [])

    def test_air_bubbles_cause_bead_voids(self):
        bubble = {"type": "air_bubble", "start_after_min": 1, "params": {"bubbles": 10, "void_probability": 0.5}}
        tmp, sim, _, truth = run(scenario("bubble", [bubble]), hours=1)
        with tmp:
            self.assertIn("BEAD_VOID", {r["ng_reason"] for r in production(sim)})
            self.assertEqual(truth["faults"][0]["state_at_end"], "resolved")

    def test_operator_calibrates_needle_for_offset_ng(self):
        offset = {"type": "needle_offset", "start_after_min": 1, "params": {"dz_mm": 0.0, "dxy_mm": 0.16}}
        tmp, _, summary, truth = run(scenario("offset", [offset]), hours=1)
        with tmp:
            self.assertIn("E4001", summary["alarms"])
            self.assertIn(truth["faults"][0]["resolved_by"], ("needle_calibration", "call_engineer"))

    def test_recipe_typo_is_visible_as_a_parameter_change(self):
        typo = {"type": "recipe_pressure_error", "start_after_min": 5, "params": {"wrong_pressure_kpa": 205}}
        tmp, sim, _, _ = run(scenario("typo", [typo]), hours=0.5)
        with tmp:
            events = (sim.log_dir / "event.log").read_text(encoding="utf-8")
            self.assertIn("Recipe parameter changed", events)
            self.assertIn("param=dispense_pressure_kpa old=250.0 new=205", events)

    def test_nozzle_clog_is_caught_and_cleaned(self):
        clog = {"type": "nozzle_clog", "start_after_min": 10, "params": {"ramp_min": 30}}
        tmp, _, summary, truth = run(scenario("nozzle_clog", [clog]), hours=2)
        with tmp:
            self.assertIn("E3005", summary["alarms"])
            fault = truth["faults"][0]
            self.assertEqual(fault["state_at_end"], "resolved")
            self.assertEqual(fault["resolved_by"], "nozzle_clean")

    def test_temp_sensor_drift_needs_engineer(self):
        drift = {"type": "temp_sensor_drift", "start_after_min": 5, "params": {"ramp_min": 30}}
        tmp, _, _, truth = run(scenario("temp_sensor_drift", [drift]), hours=3)
        with tmp:
            self.assertEqual(truth["faults"][0]["resolved_by"], "call_engineer")


if __name__ == "__main__":
    unittest.main()
