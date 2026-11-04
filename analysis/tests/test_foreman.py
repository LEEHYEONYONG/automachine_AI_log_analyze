"""LLM과 DB 없이 도는 판단 코드의 테스트."""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from app import classify, foreman, manual

T0 = datetime(2026, 10, 21, 9, 0, 0)


def rule(name, minutes):
    return {"fault_type": name, "detected_at": T0 + timedelta(minutes=minutes), "evidence": {"x": 1.5}}


def guard(feature, minutes):
    return {"fault_type": "anomaly", "detected_at": T0 + timedelta(minutes=minutes),
            "evidence": {"feature": feature, "z": 4.0}}


class Incidents(unittest.TestCase):
    def test_same_rule_repeats_stay_one_incident_even_past_an_hour(self):
        found = foreman.incidents([rule("needle_offset", m) for m in (0, 50, 100)], [])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["alerts"], 3)
        self.assertEqual(found[0]["last_at"], T0 + timedelta(minutes=100))

    def test_gap_over_an_hour_starts_a_new_incident(self):
        self.assertEqual(len(foreman.incidents([rule("air_bubble", 0), rule("air_bubble", 61)], [])), 2)

    def test_new_rule_name_is_a_separate_incident(self):
        found = foreman.incidents([rule("needle_tip_buildup", 0), rule("air_bubble", 10)], [])
        self.assertEqual([i["rule_names"] for i in found], [["needle_tip_buildup"], ["air_bubble"]])

    def test_guard_joins_the_open_incident(self):
        found = foreman.incidents([rule("vacuum_leak", 10)], [guard("vacuum_kpa", 20)])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["guard_values"], ["vacuum_kpa"])

    def test_rule_names_an_incident_the_guard_started(self):
        found = foreman.incidents([rule("vacuum_leak", 25)], [guard("vacuum_kpa", 9)])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["started_at"], T0 + timedelta(minutes=9))
        self.assertEqual(found[0]["rule_names"], ["vacuum_leak"])

    def test_lone_guard_alert_is_its_own_incident(self):
        found = foreman.incidents([], [guard("ng_10min", 0)])
        self.assertEqual(found[0]["rule_names"], [])

    def test_no_alerts(self):
        self.assertEqual(foreman.incidents([], []), [])

    def test_break_starts_a_new_incident_within_the_hour(self):
        alerts = [rule("nozzle_clog", 0), rule("nozzle_clog", 40)]
        self.assertEqual(len(foreman.incidents(alerts, [])), 1)
        found = foreman.incidents(alerts, [], breaks=[T0 + timedelta(minutes=5)])
        self.assertEqual([i["started_at"] for i in found], [T0, T0 + timedelta(minutes=40)])

    def test_alert_before_the_break_stays_in_the_old_incident(self):
        found = foreman.incidents([rule("nozzle_clog", 0)], [guard("bead_width_mm", 3)],
                                  breaks=[T0 + timedelta(minutes=5)])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["last_at"], T0 + timedelta(minutes=3))


class UnverifiedNumbers(unittest.TestCase):
    def test_flags_only_numbers_missing_from_the_sources(self):
        said = ["폭이 0.757 mm에서 0.750 mm로 줄었고 압력은 999 kPa"]
        self.assertEqual(foreman.unverified_numbers(said, ["청소 전 0.757 → 청소 후 0.75"]), ["999"])

    def test_nothing_to_check(self):
        self.assertEqual(foreman.unverified_numbers(["폭이 줄었다"], []), [])


class OtherCauses(unittest.TestCase):
    def test_flags_other_fault_names_in_english_or_korean(self):
        said = ["nozzle_clog의 증상과 일치", "공장 에어 공급압 저하는 아니다", "온도 센서 드리프트 때문"]
        self.assertEqual(foreman.other_causes_mentioned(said, "temp_sensor_drift"), ["air_supply_drop", "nozzle_clog"])

    def test_own_name_is_fine(self):
        self.assertEqual(foreman.other_causes_mentioned(["노즐 막힘 nozzle_clog"], "nozzle_clog"), [])


class Actions(unittest.TestCase):
    def test_takes_only_the_action_line_from_the_manual(self):
        found = {"section": "노즐 막힘 (nozzle_clog)", "source": "m.md", "content": "증상: 줄어든다\n구별: 청소\n조치: 1) 청소한다"}
        with mock.patch.object(manual, "section", return_value=found):
            self.assertEqual(foreman.actions_for(None, "nozzle_clog")["steps"], "1) 청소한다")

    def test_unknown_has_no_actions(self):
        self.assertIsNone(foreman.actions_for(None, classify.UNKNOWN))


class ToolPermission(unittest.TestCase):
    def test_refuses_anything_outside_the_tool_list(self):
        tools = foreman.Tools(None, {"parts": [], "maintenance": [], "changes": [], "recipes": {}},
                              {"started_at": T0, "last_at": T0, "notes": []})
        self.assertIn("없는 함수", tools.call("call", {}))
        self.assertIn("없는 함수", tools.call("__init__", {}))


class ModelAnswer(unittest.TestCase):
    def test_model_cannot_change_the_cause(self):
        ctx = {"run_id": "r", "parts": [], "maintenance": [], "changes": [], "recipes": {}}
        incident = {"started_at": T0, "last_at": T0, "rule_names": [], "guard_values": [], "notes": [], "alerts": 1,
                    "cause": classify.UNKNOWN, "basis": "x"}
        replies = [{"content": ""}, {"content": '{"cause": "nozzle_clog", "reasoning": ["근거"], "doubts": ["의문"]}'}]
        with mock.patch.object(foreman, "_chat", side_effect=replies), \
                mock.patch.object(foreman.Tools, "get_alarms", return_value=""):
            result = foreman.run(None, ctx, incident)
        self.assertEqual(result["cause"], classify.UNKNOWN)
        self.assertEqual(result["reasoning"], ["근거"])
        self.assertEqual(result["doubts"], ["의문"])


def part(minutes, width):
    return {"start_time": T0 + timedelta(minutes=minutes), "recipe": "A", "bead_width_mm": width}


class Decide(unittest.TestCase):
    def incident(self, *names):
        return {"started_at": T0, "last_at": T0, "rule_names": list(names)}

    def ctx(self, width_after):
        before = [part(m, 0.75) for m in range(50)]
        after = [part(100 + m, width_after) for m in range(30)]
        return {"parts": before + after, "maintenance": [{"ts": T0 + timedelta(minutes=60), "action": "nozzle_clean"}]}

    def test_first_rule_name_wins_over_the_tree(self):
        self.assertEqual(foreman.decide(self.ctx(0.8), self.incident("air_bubble", "needle_offset"), "vacuum_leak")[0],
                         "air_bubble")

    def test_clog_stays_when_width_recovers_after_clean(self):
        self.assertEqual(foreman.decide(self.ctx(0.8), self.incident("nozzle_clog"), None)[0], "nozzle_clog")

    def test_clog_becomes_temp_sensor_when_width_does_not_recover(self):
        self.assertEqual(foreman.decide(self.ctx(0.75), self.incident("nozzle_clog"), None)[0], "temp_sensor_drift")

    def test_clog_stays_without_a_clean_to_check(self):
        ctx = {"parts": [], "maintenance": []}
        self.assertEqual(foreman.decide(ctx, self.incident("nozzle_clog"), None)[0], "nozzle_clog")

    def test_no_rule_uses_the_tree(self):
        ctx = {"parts": [], "maintenance": []}
        self.assertEqual(foreman.decide(ctx, self.incident(), "needle_offset")[0], "needle_offset")

    def test_no_rule_and_unsure_tree_is_unknown(self):
        ctx = {"parts": [], "maintenance": []}
        self.assertEqual(foreman.decide(ctx, self.incident(), classify.UNKNOWN)[0], classify.UNKNOWN)
        self.assertEqual(foreman.decide(ctx, self.incident(), None)[0], classify.UNKNOWN)


class Sections(unittest.TestCase):
    def test_splits_on_second_level_headings_and_drops_the_preface(self):
        text = "# 제목\n머리말\n\n## 가 (a)\n내용 1\n\n## 나\n내용 2\n"
        self.assertEqual(manual.split_sections(text), [("가 (a)", "내용 1"), ("나", "내용 2")])


class Predict(unittest.TestCase):
    MODEL = {
        "features": ["z_width"], "classes": ["no_fault", "nozzle_clog"],
        "left": [1, -1, -1], "right": [2, -1, -1], "feature": [0, -2, -2], "threshold": [-3.0, -2, -2],
        "value": [[0.5, 0.5], [0.0, 1.0], [0.75, 0.25]],
    }

    def test_follows_the_tree_to_a_leaf(self):
        self.assertEqual(classify.predict(self.MODEL, {"z_width": -5.0}), ("nozzle_clog", 1.0))
        self.assertEqual(classify.predict(self.MODEL, {"z_width": 0.0}), ("no_fault", 0.75))


if __name__ == "__main__":
    unittest.main()
