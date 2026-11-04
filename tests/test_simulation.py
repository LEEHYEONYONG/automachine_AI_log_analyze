import contextlib
import copy
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
            self.assertGreater(summary["parts"], 300)
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

    def test_air_supply_drop_hits_pressure_vacuum_and_cylinders_then_recovers(self):
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
                self.assertGreater(p.fixture.achievable_vacuum_kpa, -68)
                self.assertGreater(p.cylinder_slowdown(), 1.2)
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

    def test_inline_handshake_and_ng_buffer(self):
        cfg = json.loads(json.dumps(MACHINE_CFG))
        cfg["outfeed"]["ng_buffer_capacity"] = 2
        cfg["inspection"]["random_defect_probability"] = 0.05  # make NG parts common
        tmp = tempfile.TemporaryDirectory()
        with tmp:
            sim = Simulation(cfg, scenario(), Path(tmp.name))
            summary = sim.run(1)
            events = (sim.log_dir / "event.log").read_text(encoding="utf-8")
            self.assertIn("Part sent downstream", events)
            self.assertIn("NG part to buffer", events)
            self.assertIn("Waiting for upstream", events)
            self.assertIn("E5001", summary["alarms"])
            self.assertIn("action=empty_ng_buffer", events)

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


@contextlib.contextmanager
def started(run_mode=None, **kwargs):
    """A simulation stopped at power-on, switched to a run mode, initialized and started by hand
    (the simulated crew only runs production). Closed before its folder is removed."""
    with tempfile.TemporaryDirectory() as tmp:
        sim = Simulation(copy.deepcopy(MACHINE_CFG), scenario(), Path(tmp))
        m = sim.machine
        if run_mode:
            m.set_run_mode(run_mode, by="TEST", **kwargs)
        m.init.start(clear_parts=False, by="TEST")
        while not m.init.done:
            sim.step()
        m.start(by="TEST")
        try:
            yield sim
        finally:
            sim.close()


def advance(sim, minutes):
    for _ in range(round(minutes * 60 / sim.clock.dt)):
        sim.step()
    sim.flush()


def lines(path):
    return path.read_text(encoding="utf-8").splitlines()


class RunModeTest(unittest.TestCase):
    def test_dry_run_moves_without_parts_or_adhesive(self):
        with started("DRY") as sim:
            level = sim.machine.dispenser.level_pct
            advance(sim, 5)
            m = sim.machine
            self.assertGreater(m.dry_cycles, 10)
            self.assertEqual(production(sim), [])
            self.assertEqual(m.counts.total(), 0)
            self.assertEqual(m.dispenser.level_pct, level)
            with open(sim.log_dir / "sensor_trend.csv", encoding="utf-8") as f:
                self.assertTrue(all(r["disp_valve_open"] == "0" for r in csv.DictReader(f)))
            self.assertEqual(lines(sim.log_dir / "alarm.log"), [])

    def test_dry_run_without_motion_drives_only_the_signal_tower(self):
        with started("DRY", no_motion=True) as sim:
            advance(sim, 2)
            self.assertGreater(sim.machine.dry_cycles, 3)
            with open(sim.log_dir / "io_trace.csv", encoding="utf-8") as f:
                driven = {r["signal"] for r in csv.DictReader(f) if r["address"].startswith("Y")}
            self.assertTrue(driven <= {"TOWER_GREEN", "TOWER_YELLOW", "TOWER_RED", "BUZZER"}, driven)

    def test_dummy_run_stops_after_the_set_count_and_is_not_counted(self):
        with started("DUMMY", dummy_count=4) as sim:
            advance(sim, 5)
            m = sim.machine
            self.assertEqual(m.mode.value, "STOPPED")
            self.assertEqual((m.dummy_fed, m.dummy_tray), (4, 4))
            rows = production(sim)
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(r["lot_id"] == "DUMMY" and r["wp_id"].startswith("DMY-") for r in rows))
            self.assertTrue(all(r["bead_width_mm"] for r in rows))     # the bead was really laid and inspected
            self.assertEqual(m.counts.total(), 0)
            self.assertTrue(any("Dummy run done count=4" in line for line in lines(sim.log_dir / "event.log")))
            m.start(by="TEST")                                          # START again runs a new batch
            advance(sim, 5)
            self.assertEqual(len(production(sim)), 8)

    def test_run_mode_only_changes_when_stopped_and_empty(self):
        from simulator.manual import InterlockError
        with started() as sim:
            advance(sim, 1)
            m = sim.machine
            with self.assertRaisesRegex(InterlockError, "정지 상태"):
                m.set_run_mode("DRY", by="TEST")
            m.stop(by="TEST")
            with self.assertRaisesRegex(InterlockError, "제품이 남아"):
                m.set_run_mode("DRY", by="TEST")
            with self.assertRaisesRegex(InterlockError, "알 수 없는"):
                m.set_run_mode("FAST", by="TEST")

    def test_changing_back_to_production_counts_again(self):
        with started("DUMMY", dummy_count=2) as sim:
            advance(sim, 3)
            m = sim.machine
            m.set_run_mode("PRODUCTION", by="TEST")
            m.start(by="TEST")
            advance(sim, 3)
            self.assertGreater(m.counts.total(), 10)
            self.assertTrue(all(r["lot_id"] != "DUMMY" for r in production(sim)[2:]))


class SettingsTest(unittest.TestCase):
    def test_change_is_validated_logged_and_used(self):
        from simulator.manual import InterlockError
        with started() as sim:
            m = sim.machine
            with self.assertRaisesRegex(InterlockError, "범위"):
                m.change_settings({"weight_check_interval": 5}, by="TEST")
            with self.assertRaisesRegex(InterlockError, "알 수 없는 설정"):
                m.change_settings({"tick_s": 1}, by="TEST")
            self.assertEqual(m.change_settings({"weight_check_interval": "20", "lot_size": 500}, by="TEST"),
                             ["weight_check_interval"])
            advance(sim, 10)
            events = lines(sim.log_dir / "event.log")
            self.assertTrue(any("Setting changed param=weight_check_interval old=100 new=20" in e for e in events))
            self.assertGreaterEqual(sum("Weight check OK" in e for e in events), 3)   # every 100 would be 1
            view = {s["key"]: s for s in m.settings_view()["editable"]}
            self.assertEqual((view["weight_check_interval"]["value"], view["weight_check_interval"]["standard"]), (20, 100))
            info = json.loads((sim.log_dir / "machine_info.json").read_text(encoding="utf-8"))
            self.assertEqual(info["settings"]["weight_check_interval"], 20)

    def test_counter_reset_keeps_the_log(self):
        with started() as sim:
            advance(sim, 3)
            m = sim.machine
            made = m.counts.total()
            m.reset_counters(by="TEST")
            self.assertEqual(m.counts.total(), 0)
            sim.flush()
            self.assertEqual(len(production(sim)), made)
            self.assertTrue(any("Counters reset" in e for e in lines(sim.log_dir / "event.log")))
