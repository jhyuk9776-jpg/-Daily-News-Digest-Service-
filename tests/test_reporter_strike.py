"""기자 부실 스트라이크: 선별 대표 후보 본문 판정(curate.record_representative_strike)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import curate  # noqa: E402


class RecordStrikeTest(unittest.TestCase):
    def _item(self, author="황철환 기자"):
        return {"source": "연합뉴스", "author": author, "link": "L1"}

    def test_empty_body_records_point(self):
        data = {}
        self.assertTrue(curate.record_representative_strike(data, self._item(), None, "2026-07-08"))
        self.assertEqual(data["연합뉴스::황철환"]["points"], 1)  # empty → 1점

    def test_sparse_body_records_count(self):
        data = {}
        self.assertTrue(curate.record_representative_strike(data, self._item(), "가" * 100, "2026-07-08"))
        rec = data["연합뉴스::황철환"]
        self.assertEqual(rec["sparse_count"], 1)  # 100자 < 200 → sparse
        self.assertEqual(rec["points"], 0)

    def test_normal_body_records_nothing(self):
        data = {}
        self.assertFalse(curate.record_representative_strike(data, self._item(), "가" * 300, "2026-07-08"))
        self.assertEqual(data, {})  # ≥200 → 기록 없음

    def test_no_author_skipped(self):
        data = {}
        self.assertFalse(curate.record_representative_strike(
            data, {"source": "연합뉴스", "link": "L1"}, None, "2026-07-08"))
        self.assertEqual(data, {})


if __name__ == "__main__":
    unittest.main()
