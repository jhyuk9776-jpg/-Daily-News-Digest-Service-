"""분야별 최소 교차매체(MIN_MEDIA) 오버라이드 테스트 (네트워크/API 미사용).

IT/테크는 MIN_MEDIA_BY_CAT로 2매체까지 허용, 나머지 분야는 기본 3매체.
게이트는 score_fn 주입 경로에서만 타므로 스텁 extract_fn/score_fn으로 구동한다.
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import curate  # noqa: E402

KST = timezone(timedelta(hours=9))
ISO = "2026-07-02T01:00:00+00:00"


def _art(category, source, title):
    return {"category": category, "source": source, "title": title,
            "summary": "", "link": f"L-{category}-{source}", "published_iso": ISO,
            "author": f"기자{source}"}


def _event(category, title, n_sources):
    """같은 제목을 n개 매체로 → 교차검증 n매체 클러스터 하나."""
    srcs = ["한국경제", "연합뉴스", "한겨레", "매일경제"][:n_sources]
    return [_art(category, s, title) for s in srcs]


class MinMediaOverrideTest(unittest.TestCase):
    def _run(self, raw):
        return curate.select(
            raw, datetime(2026, 7, 2, 12, 0, tzinfo=KST),
            default_limit=10, per_category_limits={"경제": 10, "IT/테크": 10},
            extract_fn=lambda link, title: "가" * 400,      # 길이 게이트 통과
            score_fn=lambda title, body: {"total": 0.8},    # REP_SCORE_FLOOR 이상
            title_penalty_fn=lambda t: 0)

    def test_it_keeps_two_media_but_econ_drops(self):
        # 두 분야 모두 '2매체 사건' 하나씩. IT/테크(min 2)는 선택, 경제(min 3)는 탈락.
        raw = {"date": "2026-07-02",
               "articles": _event("IT/테크", "AI반도체신제품", 2)
                           + _event("경제", "무역흑자확대", 2)}
        result = self._run(raw)
        self.assertEqual(len(result["categories"]["IT/테크"]), 1)
        self.assertEqual(len(result["categories"]["경제"]), 0)

    def test_econ_three_media_passes(self):
        # 경제 3매체 사건은 기본 문턱(3) 통과.
        raw = {"date": "2026-07-02", "articles": _event("경제", "금리동결결정", 3)}
        result = self._run(raw)
        self.assertEqual(len(result["categories"]["경제"]), 1)

    def test_selection_stats_carries_category_and_author(self):
        raw = {"date": "2026-07-02", "articles": _event("경제", "금리동결결정", 3)}
        result = self._run(raw)
        st = result["selection_stats"][0]
        self.assertEqual(st["category"], "경제")
        self.assertIn("winner_author", st)
        self.assertIn("winner_link", st)
        self.assertTrue(st["winner_link"].startswith("L-경제-"))


if __name__ == "__main__":
    unittest.main()
