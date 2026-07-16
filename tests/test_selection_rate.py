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


class SelectionRanksTest(unittest.TestCase):
    def test_ranked_by_rate_desc(self):
        # D6: 파이프라인 서열은 선택률 내림차순(높을수록 1위). density 아님.
        store = {"media": {
            "A": {"count": 10, "selection_rate": 0.1},
            "B": {"count": 10, "selection_rate": 0.3},
            "C": {"count": 10, "selection_rate": 0.0},
        }}
        ranks = objectivity.compute_selection_ranks(store)
        self.assertEqual(ranks["B"], 1)  # 최고 선택률
        self.assertEqual(ranks["A"], 2)
        self.assertEqual(ranks["C"], 3)

    def test_cold_start_all_zero_deterministic(self):
        # 첫날 전부 0 → 매체명 안정정렬(무순), 최신순 tie-break이 이어받음
        store = {"media": {"나": {"count": 5}, "가": {"count": 5}}}
        ranks = objectivity.compute_selection_ranks(store)
        self.assertEqual(ranks["가"], 1)  # 이름 오름차순
        self.assertEqual(ranks["나"], 2)


if __name__ == "__main__":
    unittest.main()
