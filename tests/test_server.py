import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server.app import ROOT, create_app


class ServerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(ROOT, Path(self._tmp.name), seed=7))
        self.client.__enter__()  # runs the lifespan, which starts a live run
        # Live runs start at the real clock time; without this a planned break could land mid-test.
        self.client.post("/api/operator", json={"auto": False})

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self._tmp.cleanup()

    def test_live_run_starts_stopped_and_runs_on_command(self):
        self.assertEqual(self.client.get("/api/state").json()["mode"], "STOPPED")
        self.assertEqual(self.client.post("/api/machine/start").json()["mode"], "RUNNING")
        self.assertEqual(self.client.post("/api/machine/stop").json()["mode"], "STOPPED")

    def test_maintenance_requires_stopped_machine(self):
        self.client.post("/api/machine/start")
        self.assertEqual(self.client.post("/api/maintenance", json={"action": "nozzle_clean"}).status_code, 409)
        self.client.post("/api/machine/stop")
        self.assertEqual(self.client.post("/api/maintenance", json={"action": "nozzle_clean"}).status_code, 200)
        self.assertEqual(self.client.post("/api/maintenance", json={"action": "fly"}).status_code, 400)

    def test_speed_scales_simulated_time(self):
        runner = self.client.app.state.runner
        runner.set_speed(100)
        before = runner.sim.clock.elapsed
        runner.advance(1.0)
        self.assertAlmostEqual(runner.sim.clock.elapsed - before, 100.0, delta=0.2)

    def test_fault_injection_shows_only_in_engineer_view(self):
        state = self.client.post("/api/faults", json={"type": "nozzle_clog", "params": {"ramp_min": 10}}).json()
        self.assertEqual(state["engineer"]["faults"][0]["type"], "nozzle_clog")
        self.assertIsNone(state["alarm"])

    def test_delayed_fault_waits_and_bad_params_are_rejected(self):
        state = self.client.post("/api/faults", json={"type": "vacuum_leak", "delay_min": 30}).json()
        self.assertIsNone(state["engineer"]["faults"][0]["injected_at"])
        bad = self.client.post("/api/faults", json={"type": "vacuum_leak", "params": {"nope": 1}})
        self.assertEqual(bad.status_code, 400)

    def test_trends_collect_part_values_and_downsample(self):
        runner = self.client.app.state.runner
        # Let the simulated operator clear random alarms, but without wall-clock-dependent breaks.
        runner.sim.operator.enabled = True
        runner.sim.operator.breaks = []
        runner.sim.machine.start(by="test")
        for _ in range(round(3600 / runner.sim.clock.dt)):
            runner.sim.step()
        trends = self.client.get("/api/trends", params={"minutes": 60}).json()["series"]
        widths = trends["bead_width_mm"]["points"]
        # ~400 parts averaged into at most 300 buckets (buckets during stoppages stay empty)
        self.assertTrue(200 < len(widths) <= 300, len(widths))
        self.assertTrue(all(0.6 < v < 1.0 for _, v in widths))
        self.assertGreaterEqual(len(trends["weight_check_mg"]["points"]), 3)
        self.assertEqual(trends["fixture_vac_kpa"]["limits"], {"hi": -60.0})

    def test_cycle_stop_and_log_api(self):
        runner = self.client.app.state.runner
        self.client.post("/api/machine/start")
        for _ in range(round(120 / runner.sim.clock.dt)):
            runner.sim.step()
        state = self.client.post("/api/machine/cycle_stop").json()
        self.assertTrue(state["cycle_stop"])
        self.assertTrue(state["live_log"])
        self.assertNotIn("DEBUG", {e["level"] for e in state["live_log"]})
        for _ in range(round(60 / runner.sim.clock.dt)):
            runner.sim.step()
        self.assertEqual(self.client.get("/api/state").json()["mode"], "STOPPED")

        events = self.client.get("/api/logs", params={"level": "DEBUG", "unit": "DISPENSER", "q": "step"}).json()
        self.assertTrue(events["items"])
        self.assertTrue(all(e["unit"] == "DISPENSER" for e in events["items"]))
        production = self.client.get("/api/logs", params={"kind": "production"}).json()["items"]
        self.assertIn("bead_width_mm", production[0])
        meta = self.client.get("/api/meta").json()
        self.assertEqual(meta["sequences"]["VISION"][2]["step"], "PUSH_ALIGN")

    def _steps(self, seconds):
        runner = self.client.app.state.runner
        for _ in range(round(seconds / runner.sim.clock.dt)):
            runner.sim.step()

    def test_manual_mode_interlocks_and_return_to_auto(self):
        c = self.client
        c.post("/api/machine/start")
        self.assertEqual(c.post("/api/opmode", json={"mode": "MANUAL"}).status_code, 409)  # running
        c.post("/api/machine/stop")
        self.assertEqual(c.post("/api/opmode", json={"mode": "MANUAL"}).json()["op_mode"], "MANUAL")
        self.assertEqual(c.post("/api/machine/start").json()["mode"], "STOPPED")  # START refused in MANUAL

        # pushers need the lift up first
        bad = c.post("/api/manual/device", json={"device": "VISION_PUSH_X", "on": True})
        self.assertEqual(bad.status_code, 409)
        self.assertIn("Interlock", c.get("/api/logs", params={"level": "WARN"}).json()["items"][0]["text"])
        c.post("/api/manual/device", json={"device": "VISION_LIFT", "on": True})
        self._steps(1)
        lift = next(d for d in c.get("/api/state").json()["manual"]["devices"] if d["id"] == "VISION_LIFT")
        self.assertTrue(lift["work_sensor"])
        self.assertEqual(c.post("/api/manual/device", json={"device": "VISION_PUSH_X", "on": True}).status_code, 200)

        # the needle may only go down over a lifted part, and X/Y only move with Z at a safe height
        self.assertEqual(c.post("/api/manual/axis", json={"axis": "DISP_Z", "preset": "WORK"}).status_code, 409)
        c.post("/api/manual/device", json={"device": "DISP_LIFT", "on": True})
        self._steps(1)
        self.assertEqual(c.post("/api/manual/axis", json={"axis": "DISP_Z", "preset": "WORK"}).status_code, 200)
        self._steps(3)
        self.assertEqual(c.post("/api/manual/axis", json={"axis": "DISP_X", "jog": 1}).status_code, 409)

        # a vacuum without a part on the fixture does not build up
        c.post("/api/manual/device", json={"device": "DISP_FIXTURE_VAC", "on": True})
        self._steps(1)
        vac = next(d for d in c.get("/api/state").json()["manual"]["devices"] if d["id"] == "DISP_FIXTURE_VAC")
        self.assertGreater(vac["kpa"], -10)

        self.assertEqual(c.post("/api/opmode", json={"mode": "AUTO"}).status_code, 409)  # not at auto position
        c.post("/api/manual/home_all")
        self._steps(10)
        self.assertEqual(c.post("/api/opmode", json={"mode": "AUTO"}).json()["op_mode"], "AUTO")

    def test_websocket_pushes_state(self):
        with self.client.websocket_connect("/ws") as ws:
            self.assertIn("stations", ws.receive_json())


if __name__ == "__main__":
    unittest.main()
