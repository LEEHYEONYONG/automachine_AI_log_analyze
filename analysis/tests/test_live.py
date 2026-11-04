"""실시간 감시의 파일 이어 읽기. DB와 시뮬레이터 없이 돈다."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app import live

SENSOR_HEADER = "timestamp,mode,fixture_vac_kpa,disp_pressure_kpa,disp_valve_open,disp_temp_c,syringe_level_pct\n"


class Tail(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "20261103_0800_abcdef"
        self.dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, text):
        with (self.dir / name).open("a", encoding="utf-8") as f:
            f.write(text)

    def test_reads_only_new_complete_lines_and_keeps_db_types(self):
        run = live.LiveRun(self.dir, {})
        self.write("sensor_trend.csv", SENSOR_HEADER + "2026-11-03 08:00:01.000,RUNNING,-84.8,242.5,1,35.0,99.0\n2026-11-03 08:00")
        run.update()
        self.assertEqual(len(run.sensors), 1)                       # 쓰는 도중인 둘째 줄은 아직 안 읽음
        first = run.sensors[0]
        self.assertEqual(first["ts"], datetime(2026, 11, 3, 8, 0, 1))
        self.assertEqual((first["disp_valve_open"], first["fixture_vac_kpa"]), (1, -84.8))
        self.write("sensor_trend.csv", ":02.000,RUNNING,-84.7,242.4,0,35.0,98.9\n")
        run.update()
        self.assertEqual([s["ts"].second for s in run.sensors], [1, 2])

    def test_reads_setting_and_run_mode_changes(self):
        run = live.LiveRun(self.dir, {})
        self.write("event.log",
                   "2026-11-03 09:00:00.000 INFO  HMI        Setting changed param=weight_check_interval old=100 new=20 by=ENG01\n"
                   "2026-11-03 09:01:00.000 INFO  MACHINE    Run mode change run_mode=DUMMY dummy_count=5 no_motion=0 by=ENG01\n"
                   "2026-11-03 09:02:00.000 INFO  MACHINE    Mode change mode=RUNNING by=ENG01\n")
        run.update()
        events = run.context()["machine_events"]
        self.assertEqual([e["attrs"].get("param") or e["attrs"].get("run_mode") for e in events], ["weight_check_interval", "DUMMY"])

    def test_missing_files_are_fine(self):
        run = live.LiveRun(self.dir, {})
        self.assertEqual(run.update(), 0)
        self.assertIsNone(run.now())

    def test_events_and_alarms(self):
        run = live.LiveRun(self.dir, {})
        self.write("event.log",
                   "2026-11-03 09:00:00.000 INFO  HMI        Recipe parameter changed recipe=A param=retract_delay_s old=0.3 new=0.0 by=OP-A\n"
                   "2026-11-03 09:10:00.000 INFO  MAINT      Maintenance done action=nozzle_clean by=OP-A\n")
        self.write("alarm.log",
                   "2026-11-03 09:20:00.000 SET   E3005 DISPENSER  Weight check out of spec | weight=9.9mg\n"
                   "2026-11-03 09:21:00.000 CLEAR E3005 DISPENSER  Weight check out of spec\n")
        run.update()
        self.assertEqual(run.changes[0]["attrs"]["new"], "0.0")
        self.assertEqual(run.maintenance[0]["action"], "nozzle_clean")
        self.assertEqual([a["code"] for a in run.alarms], ["E3005"])   # 해제 줄은 세지 않음

    def test_production_sorted_by_start(self):
        run = live.LiveRun(self.dir, {})
        self.write("production.csv", "wp_id,recipe,start_time,end_time,bead_width_mm,ng_reason\n"
                   "W2,A,2026-11-03 08:00:10.000,2026-11-03 08:00:20.000,0.79,\n"
                   "W1,A,2026-11-03 08:00:05.000,2026-11-03 08:00:21.000,0.78,STRINGING\n")
        run.update()
        self.assertEqual([p["wp_id"] for p in run.parts], ["W1", "W2"])
        self.assertIsNone(run.parts[1]["ng_reason"])


class LeadTime(unittest.TestCase):
    def test_related_alarm_after_the_alert(self):
        self.assertIn("E3005", live.RELATED_ALARMS["nozzle_clog"])
        self.assertIn("E3001", live.RELATED_ALARMS["vacuum_leak"])


if __name__ == "__main__":
    unittest.main()
