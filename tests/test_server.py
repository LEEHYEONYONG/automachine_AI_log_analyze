import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server.app import ROOT, create_app


class ServerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # No real-time loop: the tests step the simulation themselves, from this thread only.
        self.client = TestClient(create_app(ROOT, Path(self._tmp.name), seed=7, live=False))
        self.client.__enter__()  # runs the lifespan, which starts a live run
        # Live runs start at the real clock time; without this a planned break could land mid-test.
        self.client.post("/api/operator", json={"auto": False})
        # Most tests act as the machine maker, who may do everything; permissions have their own test.
        self.client.post("/api/login", json={"user": "MAKER", "pin": "9999"})
        # Power-on state needs an initialization before START, like the real machine.
        self.client.post("/api/initialize", json={"clear_parts": False})
        self._steps(15)

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

    def test_permissions_by_login_level(self):
        c = self.client
        c.post("/api/logout")
        self.assertEqual(c.get("/api/state").json()["hmi"]["level"], "GUEST")
        self.assertEqual(c.post("/api/machine/start").status_code, 403)
        self.assertEqual(c.post("/api/machine/stop").status_code, 200)  # stopping is always allowed
        self.assertEqual(c.post("/api/login", json={"user": "OP01", "pin": "0000"}).status_code, 401)

        state = c.post("/api/login", json={"user": "OP01", "pin": "1111"}).json()
        self.assertEqual(state["hmi"]["level"], "OPERATOR")
        self.assertFalse(state["hmi"]["permissions"]["manual"])
        self.assertEqual(c.post("/api/machine/start").json()["mode"], "RUNNING")
        c.post("/api/machine/stop")
        self.assertEqual(c.post("/api/opmode", json={"mode": "MANUAL"}).status_code, 403)
        self.assertEqual(c.post("/api/maintenance", json={"action": "nozzle_clean"}).status_code, 200)
        self.assertEqual(c.post("/api/maintenance", json={"action": "needle_calibration"}).status_code, 403)

        c.post("/api/login", json={"user": "ENG01", "pin": "2222"})
        self.assertEqual(c.post("/api/opmode", json={"mode": "MANUAL"}).json()["op_mode"], "MANUAL")
        self.assertEqual(c.post("/api/maintenance", json={"action": "needle_calibration"}).status_code, 200)

        texts = [e["text"] for e in c.get("/api/logs", params={"limit": 100}).json()["items"]]
        self.assertTrue(any("by=OP01" in t for t in texts))
        self.assertTrue(any(t.startswith("Access denied") for t in
                            [e["text"] for e in c.get("/api/logs", params={"level": "WARN"}).json()["items"]]))

    def test_emergency_stop_and_safety_door(self):
        c = self.client

        def io():
            return {s["id"]: s["value"] for s in c.get("/api/io").json()["inputs"]}

        # E-stop while running: alarm, outputs off, re-initialization needed, no reset until released
        c.post("/api/machine/start")
        self._steps(10)
        state = c.post("/api/safety/estop", json={"pressed": True}).json()
        self.assertEqual((state["mode"], state["alarm"]["code"]), ("ALARM", "E9100"))
        self.assertEqual(state["init"]["state"], "REQUIRED")
        self.assertFalse(state["dispenser_valve_open"] or state["fixture_vacuum_on"])
        self._steps(0.2)
        self.assertFalse(io()["ESTOP_OK"])
        self.assertEqual(c.post("/api/machine/reset").status_code, 409)
        c.post("/api/safety/estop", json={"pressed": False})
        self.assertEqual(c.post("/api/machine/reset").json()["mode"], "STOPPED")
        self.assertEqual(c.post("/api/machine/start").json()["mode"], "STOPPED")  # initialize first
        c.post("/api/initialize", json={"clear_parts": False})
        self._steps(15)
        self.assertEqual(c.post("/api/machine/start").json()["mode"], "RUNNING")

        # door opened while running: alarm; START and initialize refused until it is closed
        self._steps(5)
        state = c.post("/api/safety/door", json={"door": "FRONT_LEFT", "open": True}).json()
        self.assertEqual(state["alarm"]["code"], "E9101")
        self._steps(0.2)
        self.assertFalse(io()["DOOR_FL_CLOSED"])
        self.assertEqual(c.post("/api/machine/reset").status_code, 409)
        c.post("/api/safety/door", json={"door": "FRONT_LEFT", "open": False})
        c.post("/api/machine/reset")
        self.assertEqual(c.get("/api/state").json()["init"]["state"], "DONE")  # a door does not need re-init
        c.post("/api/safety/door", json={"door": "FRONT_RIGHT", "open": True})
        self.assertEqual(c.post("/api/machine/start").status_code, 409)
        self.assertEqual(c.post("/api/initialize", json={"clear_parts": False}).status_code, 409)
        c.post("/api/safety/door", json={"door": "FRONT_RIGHT", "open": False})
        self.assertEqual(c.post("/api/machine/start").json()["mode"], "RUNNING")

    def test_recipe_edit_limits_permissions_and_physics(self):
        c = self.client
        data = c.get("/api/recipes").json()
        self.assertEqual(data["current"], "REAR_HOUSING_ADH_A")
        self.assertIn("dispense_pressure_kpa", data["spec"])

        # out of range values are refused with the reason
        bad = c.post("/api/recipes/REAR_HOUSING_ADH_A", json={"values": {"dispense_pressure_kpa": 900}})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("100~400", bad.json()["detail"])

        # only the maker may edit; an engineer may load
        c.post("/api/login", json={"user": "ENG01", "pin": "2222"})
        self.assertEqual(c.post("/api/recipes/REAR_HOUSING_ADH_A", json={"values": {"dispense_pressure_kpa": 270}}).status_code, 403)
        c.post("/api/login", json={"user": "MAKER", "pin": "9999"})
        res = c.post("/api/recipes/REAR_HOUSING_ADH_A", json={"values": {"dispense_pressure_kpa": 270}}).json()
        self.assertEqual(res["changed"], ["dispense_pressure_kpa"])
        self.assertEqual(res["setpoints"]["dispense_pressure_kpa"], 270)
        self.assertTrue(res["history"][0]["text"].startswith("Recipe edited"))

        # physics follows the edit: 8% more pressure gives about 8% more adhesive
        m = c.app.state.runner.sim.machine
        self._steps(0.2)  # the regulator follows the new setpoint on the next tick
        weights =[m.dispenser._shot(m.setpoints["dispense_time_s"]).weight_mg for _ in range(200)]
        self.assertAlmostEqual(sum(weights) / len(weights), 12.0 * 270 / 250, delta=0.15)

        c.post("/api/login", json={"user": "ENG01", "pin": "2222"})
        self.assertEqual(c.post("/api/recipes/REAR_HOUSING_ADH_B/load").json()["current"], "REAR_HOUSING_ADH_B")

    def test_initialize_gates_start_and_handles_parts_left_in_the_line(self):
        c = self.client
        self.assertEqual(c.get("/api/state").json()["init"]["state"], "DONE")
        c.post("/api/machine/start")
        self._steps(25)
        c.post("/api/machine/stop")  # stopped mid-cycle with parts in several stations

        # moving something by hand means AUTO needs a fresh initialization
        c.post("/api/opmode", json={"mode": "MANUAL"})
        c.post("/api/manual/home_all")
        self._steps(10)
        state = c.post("/api/opmode", json={"mode": "AUTO"}).json()
        self.assertEqual(state["init"]["state"], "REQUIRED")
        self.assertEqual(c.post("/api/machine/start").json()["mode"], "STOPPED")

        # keep the parts: stations restart, nothing is lost
        before = sum(c.get("/api/state").json()["counts"].values())
        wip = [s["wp"] for s in c.get("/api/state").json()["stations"] if s["wp"]]
        self.assertTrue(wip)
        c.post("/api/initialize", json={"clear_parts": False})
        self.assertEqual(c.get("/api/state").json()["init"]["state"], "RUNNING")
        self.assertEqual(c.post("/api/machine/start").json()["mode"], "STOPPED")  # not while initializing
        self._steps(15)
        state = c.get("/api/state").json()
        self.assertEqual(state["init"]["state"], "DONE")
        self.assertEqual([s["wp"] for s in state["stations"] if s["wp"]], wip)
        self.assertEqual(sum(state["counts"].values()), before)
        self.assertIn("Initialize done", c.get("/api/logs", params={"q": "Initialize"}).json()["items"][0]["text"])
        self.assertEqual(c.post("/api/machine/start").json()["mode"], "RUNNING")
        self._steps(30)
        c.post("/api/machine/stop")

        # clear the parts: everything in the line is scrapped as removed by the operator
        c.post("/api/opmode", json={"mode": "MANUAL"})
        c.post("/api/manual/device", json={"device": "INFEED_BELT", "on": True})
        c.post("/api/manual/home_all")
        self._steps(5)
        c.post("/api/opmode", json={"mode": "AUTO"})
        wip = [s["wp"] for s in c.get("/api/state").json()["stations"] if s["wp"]]
        c.post("/api/initialize", json={"clear_parts": True})
        self._steps(15)
        state = c.get("/api/state").json()
        self.assertTrue(all(s["wp"] is None and s["state"] == "IDLE" for s in state["stations"]))
        scrapped = [r for r in c.get("/api/logs", params={"kind": "production"}).json()["items"]
                    if r["ng_reason"] == "SCRAP_INIT"]
        self.assertEqual(sorted(r["wp_id"] for r in scrapped), sorted(wip))

    def test_io_follows_sequence_and_can_be_forced_in_manual(self):
        c = self.client
        io = c.get("/api/io").json()
        by_id = {s["id"]: s for s in io["inputs"] + io["outputs"]}
        self.assertTrue(by_id["ESTOP_OK"]["value"])
        self.assertTrue(by_id["VISION_LIFT_DOWN_SNS"]["value"])
        self.assertTrue(by_id["TOWER_YELLOW"]["value"])
        self.assertRegex(by_id["VISION_LIFT_UP_SOL"]["address"], r"^Y[0-7]{3}$")

        # in AUTO the lift solenoid comes on during the vision sequence
        c.post("/api/machine/start")
        seen_up = False
        runner = c.app.state.runner
        for _ in range(round(30 / runner.sim.clock.dt)):
            runner.sim.step()
            seen_up |= runner.sim.machine.io.values[by_id["VISION_LIFT_UP_SNS"]["address"]]
        self.assertTrue(seen_up)
        c.post("/api/machine/stop")

        # forcing is refused in AUTO and drives the device in MANUAL (interlocks still apply)
        addr = by_id["VISION_PUSH_X_SOL"]["address"]
        self.assertEqual(c.post("/api/io/force", json={"address": addr, "value": True}).status_code, 409)
        c.post("/api/manual/home_all")  # not allowed in AUTO either
        c.post("/api/opmode", json={"mode": "MANUAL"})
        c.post("/api/manual/home_all")
        self._steps(5)
        self.assertEqual(c.post("/api/io/force", json={"address": addr, "value": True}).status_code, 409)  # lift down
        lift = by_id["VISION_LIFT_UP_SOL"]["address"]
        self.assertEqual(c.post("/api/io/force", json={"address": lift, "value": True}).status_code, 200)
        self._steps(1)
        io = {s["id"]: s["value"] for s in c.get("/api/io").json()["inputs"]}
        self.assertTrue(io["VISION_LIFT_UP_SNS"])
        self.assertFalse(io["VISION_LIFT_DOWN_SNS"])

    def test_websocket_pushes_state(self):
        with self.client.websocket_connect("/ws") as ws:
            self.assertIn("stations", ws.receive_json())


if __name__ == "__main__":
    unittest.main()
