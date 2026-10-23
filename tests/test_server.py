import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server.app import ROOT, create_app


class ServerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(ROOT, Path(self._tmp.name)))
        self.client.__enter__()  # runs the lifespan, which starts a live run

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

    def test_websocket_pushes_state(self):
        with self.client.websocket_connect("/ws") as ws:
            self.assertIn("stations", ws.receive_json())


if __name__ == "__main__":
    unittest.main()
