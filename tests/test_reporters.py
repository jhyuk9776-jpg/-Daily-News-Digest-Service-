"""기자 부실 스트라이크 모듈 테스트 (네트워크/API 미사용)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import reporters  # noqa: E402


class NormalizeAuthorTest(unittest.TestCase):
    def test_strips_reporter_suffix(self):
        self.assertEqual(reporters.normalize_author("김송이 기자"), "김송이")

    def test_trims_whitespace(self):
        self.assertEqual(reporters.normalize_author("  황철환  "), "황철환")

    def test_plain_name_unchanged(self):
        self.assertEqual(reporters.normalize_author("이원지"), "이원지")


class ReporterKeyTest(unittest.TestCase):
    def test_key_scopes_by_source(self):
        self.assertEqual(reporters.reporter_key("연합뉴스", "황철환 기자"), "연합뉴스::황철환")


class ClassifyBodyTest(unittest.TestCase):
    def test_none_is_empty(self):
        self.assertEqual(reporters.classify_body(None), "empty")

    def test_short_body_is_sparse(self):
        self.assertEqual(reporters.classify_body("가" * 150), "sparse")

    def test_boundary_200_is_ok(self):
        self.assertIsNone(reporters.classify_body("가" * 200))

    def test_long_body_is_ok(self):
        self.assertIsNone(reporters.classify_body("가" * 500))


class RecordStrikeTest(unittest.TestCase):
    def test_empty_adds_one_point(self):
        data = reporters.record_strike({}, "연합뉴스", "황철환", "2026-07-08", "L1", "empty", 0)
        rec = data["연합뉴스::황철환"]
        self.assertEqual(rec["points"], 1)
        self.assertFalse(rec["blacklisted"])

    def test_three_empties_blacklist(self):
        data = {}
        for i in range(3):
            data = reporters.record_strike(data, "연합뉴스", "황철환", "2026-07-08",
                                           f"L{i}", "empty", 0)
        self.assertTrue(data["연합뉴스::황철환"]["blacklisted"])

    def test_three_sparse_make_one_point_and_reset(self):
        data = {}
        for i in range(3):
            data = reporters.record_strike(data, "연합뉴스", "황철환", "2026-07-08",
                                           f"L{i}", "sparse", 120)
        rec = data["연합뉴스::황철환"]
        self.assertEqual(rec["points"], 1)
        self.assertEqual(rec["sparse_count"], 0)

    def test_two_sparse_no_point_yet(self):
        data = {}
        for i in range(2):
            data = reporters.record_strike(data, "연합뉴스", "황철환", "2026-07-08",
                                           f"L{i}", "sparse", 120)
        rec = data["연합뉴스::황철환"]
        self.assertEqual(rec["points"], 0)
        self.assertEqual(rec["sparse_count"], 2)

    def test_duplicate_date_link_is_noop(self):
        data = reporters.record_strike({}, "연합뉴스", "황철환", "2026-07-08", "L1", "empty", 0)
        data = reporters.record_strike(data, "연합뉴스", "황철환", "2026-07-08", "L1", "empty", 0)
        rec = data["연합뉴스::황철환"]
        self.assertEqual(rec["points"], 1)
        self.assertEqual(len(rec["history"]), 1)

    def test_history_records_reason_and_chars(self):
        data = reporters.record_strike({}, "연합뉴스", "황철환", "2026-07-08", "L1", "sparse", 123)
        h = data["연합뉴스::황철환"]["history"][0]
        self.assertEqual(h, {"date": "2026-07-08", "link": "L1",
                             "reason": "sparse", "chars": 123})


class BlacklistedKeysTest(unittest.TestCase):
    def test_returns_only_blacklisted(self):
        data = {
            "A::x": {"blacklisted": True, "points": 3, "sparse_count": 0, "history": []},
            "B::y": {"blacklisted": False, "points": 1, "sparse_count": 0, "history": []},
        }
        self.assertEqual(reporters.blacklisted_keys(data), {"A::x"})


class LoadSaveTest(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(reporters, "REPORTERS_FILE", Path(tmp) / "reporters.json"):
                self.assertEqual(reporters.load(), {})

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(reporters, "REPORTERS_FILE", Path(tmp) / "reporters.json"):
                reporters.save({"연합뉴스::황철환": {"points": 1}})
                self.assertEqual(reporters.load(), {"연합뉴스::황철환": {"points": 1}})


class RecordSelectionTest(unittest.TestCase):
    def test_first_selection_counts_one(self):
        data = reporters.record_selection({}, "연합뉴스", "김진성", "2026-07-23", "L1")
        self.assertEqual(data["연합뉴스::김진성"]["selected_count"], 1)

    def test_duplicate_date_link_is_noop(self):
        data = reporters.record_selection({}, "연합뉴스", "김진성", "2026-07-23", "L1")
        data = reporters.record_selection(data, "연합뉴스", "김진성", "2026-07-23", "L1")
        self.assertEqual(data["연합뉴스::김진성"]["selected_count"], 1)

    def test_different_link_increments(self):
        data = reporters.record_selection({}, "연합뉴스", "김진성", "2026-07-23", "L1")
        data = reporters.record_selection(data, "연합뉴스", "김진성", "2026-07-23", "L2")
        self.assertEqual(data["연합뉴스::김진성"]["selected_count"], 2)

    def test_suffix_normalized_same_key(self):
        data = reporters.record_selection({}, "연합뉴스", "김진성 기자", "2026-07-23", "L1")
        self.assertIn("연합뉴스::김진성", data)

    def test_coexists_with_strike_record(self):
        data = reporters.record_strike({}, "연합뉴스", "김진성", "2026-07-23", "S1", "empty", 0)
        data = reporters.record_selection(data, "연합뉴스", "김진성", "2026-07-23", "L1")
        rec = data["연합뉴스::김진성"]
        self.assertEqual(rec["points"], 1)          # 스트라이크 보존
        self.assertEqual(rec["selected_count"], 1)  # 선택 카운트 공존


if __name__ == "__main__":
    unittest.main()
