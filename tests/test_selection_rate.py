"""선택률 평판 누적 테스트 (win/appear 정규화, 날짜 멱등)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import objectivity  # noqa: E402


class SelectionRateTest(unittest.TestCase):
    def _empty(self):
        return {"media": {}, "processed_dates": [], "selection_dates": []}

    def test_accumulate_and_rate(self):
        stats = [
            {"members": ["연합뉴스", "한국경제"], "winner": "한국경제"},
            {"members": ["연합뉴스", "SBS"], "winner": "연합뉴스"},
        ]
        s = objectivity.update_selection_rates(self._empty(), stats, "2026-07-15")
        self.assertEqual(s["media"]["연합뉴스"]["appear_total"], 2)
        self.assertEqual(s["media"]["연합뉴스"]["win_total"], 1)
        self.assertEqual(s["media"]["연합뉴스"]["selection_rate"], 0.5)
        self.assertEqual(s["media"]["한국경제"]["selection_rate"], 1.0)

    def test_idempotent_by_date(self):
        stats = [{"members": ["연합뉴스", "한국경제"], "winner": "한국경제"}]
        s = objectivity.update_selection_rates(self._empty(), stats, "2026-07-15")
        s = objectivity.update_selection_rates(s, stats, "2026-07-15")  # 재실행
        self.assertEqual(s["media"]["연합뉴스"]["appear_total"], 1)


if __name__ == "__main__":
    unittest.main()
