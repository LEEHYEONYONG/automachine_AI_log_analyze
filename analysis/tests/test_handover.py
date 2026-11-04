"""교대 인수인계의 코드 부분 테스트 (LLM과 DB 없이)."""
import unittest
from datetime import datetime, timedelta

from app import handover

DAY = datetime(2026, 10, 21)


def at(h, m=0):
    return DAY + timedelta(hours=h, minutes=m)


def ctx(parts=(), maintenance=(), changes=()):
    return {"recipes": {"A": {"dispense_pressure_kpa": 250.0}}, "parts": list(parts),
            "maintenance": list(maintenance), "changes": list(changes)}


class Shifts(unittest.TestCase):
    def test_cuts_at_shift_starts(self):
        found = handover.shifts(at(9), at(22))
        self.assertEqual([(s.hour, lo.hour, hi.hour) for s, lo, hi in found], [(8, 9, 20), (20, 20, 22)])

    def test_short_leftover_shift_is_dropped(self):
        parts = [{"start_time": at(8), "ng_reason": None}, {"start_time": at(20, 30), "ng_reason": None}]
        self.assertEqual(len(handover.shift_list(ctx(parts), [], [])), 1)


class Facts(unittest.TestCase):
    def test_counts_alarms_actions_and_defects(self):
        parts = [{"start_time": at(9), "ng_reason": None}, {"start_time": at(10), "ng_reason": "WIDTH_LOW"}]
        alarms = [{"code": "E3005", "set_ts": at(9, 30), "message": "Weight check out of spec"}] * 2
        items = handover.facts(ctx(parts, [{"ts": at(9, 40), "action": "nozzle_clean"}]), alarms, [], at(8), at(20))
        texts = [f["text"] for f in items]
        self.assertIn("알람 E3005 Weight check out of spec 2회 (09:30, 09:30).", texts)
        self.assertIn("정비: 노즐 청소 1회.", texts)
        self.assertIn("생산: 2개, 그중 불량 1개.", texts)
        self.assertIn("불량 사유: 폭 미달 1개.", texts)

    def test_alert_near_the_end_is_open(self):
        incidents = [{"started_at": at(19), "last_at": at(19, 50), "cause": "nozzle_clog"},
                     {"started_at": at(10), "last_at": at(11), "cause": "vacuum_leak"}]
        items = handover.facts(ctx(), [], incidents, at(8), at(20))
        self.assertEqual([f.get("open") for f in items if f["text"].startswith("AI")], [True, False])

    def test_recipe_change_shows_standard(self):
        change = {"ts": at(11), "attrs": {"recipe": "A", "param": "dispense_pressure_kpa", "old": "250.0", "new": "205.0"}}
        items = handover.facts(ctx(changes=[change]), [], [], at(8), at(20))
        self.assertIn("설정 변경: 11:00 토출 압력 250.0 → 205.0 (표준 250.0).", [f["text"] for f in items])

    def test_dummy_parts_are_kept_apart_from_production(self):
        parts = [{"start_time": at(9), "ng_reason": None, "lot_id": "L1"},
                 {"start_time": at(10), "ng_reason": "WIDTH_LOW", "lot_id": "DUMMY"},
                 {"start_time": at(10, 1), "ng_reason": None, "lot_id": "DUMMY"}]
        texts = [f["text"] for f in handover.facts(ctx(parts), [], [], at(8), at(20))]
        self.assertIn("생산: 1개, 그중 불량 0개.", texts)
        self.assertIn("더미 런: 더미 제품 2개 (생산 수 제외).", texts)
        self.assertFalse(any(t.startswith("불량 사유") for t in texts))   # the dummy NG is not a production defect

    def test_machine_setting_and_run_mode_changes(self):
        events = [{"ts": at(9), "message": "Setting changed", "attrs": {"param": "weight_check_interval", "old": "100", "new": "20"}},
                  {"ts": at(9, 30), "message": "Run mode change", "attrs": {"run_mode": "DRY"}}]
        c = ctx()
        c["machine_events"] = events
        texts = [f["text"] for f in handover.facts(c, [], [], at(8), at(20))]
        self.assertIn("장비 설정 변경: 09:00 중량 검사 주기 100 → 20.", texts)
        self.assertIn("운전 방식 변경: 09:30 드라이 런.", texts)


class Priorities(unittest.TestCase):
    def test_open_first_then_latest_alert(self):
        items = [{"text": "AI 경보 a", "need": ["a"]}, {"text": "AI 경보 b", "need": ["b"]},
                 {"text": "AI 경보 c", "need": ["c"], "open": True}]
        self.assertEqual([f["text"] for f in handover.priorities(items)], ["AI 경보 c", "AI 경보 b"])

    def test_without_alerts_uses_the_most_frequent_alarm(self):
        items = [{"text": "알람 E1", "need": ["E1", "1회"]}, {"text": "알람 E2", "need": ["E2", "4회"]}]
        self.assertEqual(handover.priorities(items), [{"text": "알람 E2", "need": ["E2"]}])


class Check(unittest.TestCase):
    def test_finds_missing_and_made_up(self):
        items = [{"text": "AI 경보: 10:14부터 노즐 막힘 의심", "need": ["노즐 막힘"]}]
        result = handover.check("- 10:14부터 시린지 기포, E3005가 3회", items, "사실 1개")
        self.assertEqual(result["missing"], ["AI 경보: 10:14부터 노즐 막힘 의심"])
        self.assertEqual(result["made_up_codes"], ["E3005"])
        self.assertEqual(result["made_up_numbers"], ["3", "3005"])
        self.assertEqual(result["made_up_times"], [])     # 한글이 붙은 10:14도 사실에서 찾는다


if __name__ == "__main__":
    unittest.main()
