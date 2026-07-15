"""대표 선정(길이필터+채점) + density 3위 라운드로빈 백필 테스트(주입식, 네트워크 없음)."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import curate  # noqa: E402

KST = timezone(timedelta(hours=9))


class PickRepresentativeTest(unittest.TestCase):
    def _cluster(self, *members):
        return {"members": list(members)}

    def test_picks_highest_score_within_length(self):
        cluster = self._cluster(
            {"source": "A", "link": "x", "title": "T", "category": "경제"},
            {"source": "B", "link": "y", "title": "T", "category": "경제"},
        )
        bodies = {"x": "짧음", "y": "좋은 본문 " * 100}  # x<300 제외, y 유효
        excluded = []
        rep = curate.pick_representative(
            cluster, lambda link, title="": bodies[link],
            lambda title, body: {"total": 0.9}, {}, excluded)
        self.assertEqual(rep["link"], "y")
        self.assertEqual(len(excluded), 1)          # x 길이 이탈 기록
        self.assertEqual(excluded[0]["link"], "x")

    def test_tie_broken_by_density_rank(self):
        cluster = self._cluster(
            {"source": "A", "link": "x", "title": "T", "category": "경제"},
            {"source": "B", "link": "y", "title": "T", "category": "경제"},
        )
        body = "본문 " * 200  # 유효 길이
        ranks = {"A": 2, "B": 1}  # B가 우선(rank 낮음)
        rep = curate.pick_representative(
            cluster, lambda link, title="": body,
            lambda title, b: {"total": 0.5}, ranks, [])
        self.assertEqual(rep["source"], "B")        # 동점 → density 우선

    def test_none_when_all_out_of_range(self):
        cluster = self._cluster({"source": "A", "link": "x", "title": "T", "category": "경제"})
        rep = curate.pick_representative(
            cluster, lambda link, title="": "짧", lambda t, b: {"total": 1.0}, {}, [])
        self.assertIsNone(rep)


class BackfillTest(unittest.TestCase):
    def test_round_robin_top3_only(self):
        iso = "2026-07-15T09:00:00+09:00"
        solo = [
            {"source": "A", "link": "a1", "published_iso": iso},
            {"source": "A", "link": "a2", "published_iso": iso},
            {"source": "B", "link": "b1", "published_iso": iso},
            {"source": "C", "link": "c1", "published_iso": iso},
            {"source": "D", "link": "d1", "published_iso": iso},  # 4위 → 제외
        ]
        ranks = {"A": 1, "B": 2, "C": 3, "D": 4}
        out = curate.backfill_round_robin(solo, ranks, need=4)
        self.assertEqual([c["link"] for c in out], ["a1", "b1", "c1", "a2"])
        self.assertNotIn("d1", [c["link"] for c in out])

    def test_stops_at_need(self):
        iso = "2026-07-15T09:00:00+09:00"
        solo = [{"source": "A", "link": f"a{i}", "published_iso": iso} for i in range(5)]
        ranks = {"A": 1}
        out = curate.backfill_round_robin(solo, ranks, need=2)
        self.assertEqual(len(out), 2)


class SelectIntegrationTest(unittest.TestCase):
    def _art(self, title, source, link):
        return {"title": title, "source": source, "link": link, "category": "경제",
                "summary": "", "published_iso": "2026-07-15T09:00:00+09:00"}

    def test_body_scoring_length_filter_and_backfill(self):
        arts = [
            self._art("금리 동결 결정", "A", "c1"),   # 교차검증 쌍
            self._art("금리 동결 결정", "B", "c2"),
            self._art("환율 급등 마감", "A", "s1"),   # 단독
            self._art("유가 하락 지속", "B", "s2"),   # 단독
        ]
        raw = {"date": "2026-07-15", "articles": arts}
        today = datetime(2026, 7, 15, 12, tzinfo=KST)
        good = "본문 " * 200
        bodies = {"c1": good, "c2": "짧", "s1": good, "s2": good}  # c2는 길이 미달
        result = curate.select(
            raw, {}, today, default_limit=2,
            extract_fn=lambda link, title="": bodies[link],
            score_fn=lambda title, body: {"total": 0.5},
            ranks={"A": 1, "B": 2})
        econ = result["categories"]["경제"]
        self.assertEqual(len(econ), 2)                    # 교차검증 1 + 백필 1
        self.assertEqual(econ[0]["corroboration_count"], 2)
        self.assertEqual(econ[0]["link"], "c1")           # c2 길이미달 → c1 대표
        self.assertEqual(econ[1]["corroboration_count"], 1)  # 백필 단독
        self.assertNotIn("members", econ[0])              # 경량화
        excluded_links = [e["link"] for e in result["length_excluded"]]
        self.assertIn("c2", excluded_links)
        # 교차검증 클러스터만 평판 통계 배출(단독 백필 제외)
        self.assertEqual(len(result["selection_stats"]), 1)
        self.assertEqual(set(result["selection_stats"][0]["members"]), {"A", "B"})
        self.assertEqual(result["selection_stats"][0]["winner"], "A")  # c1(A) 대표


if __name__ == "__main__":
    unittest.main()
