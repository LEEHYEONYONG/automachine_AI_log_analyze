import json
import tempfile
import unittest
from pathlib import Path

from simulator.simulation import Simulation

ROOT = Path(__file__).resolve().parent.parent
MACHINE_CFG = json.loads((ROOT / "config" / "machine.json").read_text(encoding="utf-8"))


def scenario(name="test", faults=(), seed=1):
    return {"name": name, "start_time": "2026-10-19T08:00:00", "seed": seed, "faults": list(faults)}


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
        clog = {"type": "nozzle_clog", "start_after_min": 5, "params": {"ramp_min": 20}}
        tmp, sim, _, _ = run(scenario("nozzle_clog", [clog]), hours=0.5)
        with tmp:
            self.assertNotIn("clog", sim.run_id)
            for path in sim.log_dir.iterdir():
                self.assertNotIn("clog", path.read_text(encoding="utf-8").lower(), path.name)

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
