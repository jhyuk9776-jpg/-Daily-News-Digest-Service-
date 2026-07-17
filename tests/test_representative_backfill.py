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

    def test_tie_broken_by_recency_when_ranks_equal(self):
        # D7: 선택률 동률(첫날 등 ranks 무의미)이면 최신순으로 대표 선정.
        cluster = self._cluster(
            {"source": "A", "link": "old", "title": "T", "category": "경제",
             "published_iso": "2026-07-15T09:00:00+09:00"},
            {"source": "B", "link": "new", "title": "T", "category": "경제",
             "published_iso": "2026-07-16T09:00:00+09:00"},
        )
        rep = curate.pick_representative(
            cluster, lambda link, title="": "본문 " * 100,
            lambda t, b: {"total": 0.5}, {}, [])   # ranks 비어있음 → 동률
        self.assertEqual(rep["link"], "new")        # 최신 기사

    def test_none_when_all_out_of_range(self):
        cluster = self._cluster({"source": "A", "link": "x", "title": "T", "category": "경제"})
        rep = curate.pick_representative(
            cluster, lambda link, title="": "짧", lambda t, b: {"total": 1.0}, {}, [])
        self.assertIsNone(rep)

    def test_on_body_called_for_each_member(self):
        cluster = self._cluster(
            {"source": "A", "link": "x", "title": "T", "category": "경제"},
            {"source": "B", "link": "y", "title": "T", "category": "경제"},
        )
        seen = []
        curate.pick_representative(
            cluster, lambda link, title="": "본문 " * 200, lambda t, b: {"total": 0.5},
            {}, [], on_body=lambda m, body: seen.append(m["link"]))
        self.assertEqual(set(seen), {"x", "y"})   # 스트라이크 판정용 콜백이 멤버마다 호출

    def test_clickbait_title_excluded(self):
        # D4: 제목 낚시(감점>0)는 대표 후보에서 하드 배제. 깨끗한 제목이 대표.
        cluster = self._cluster(
            {"source": "A", "link": "x", "title": "이대로 괜찮을까?", "category": "경제"},
            {"source": "B", "link": "y", "title": "한은 기준금리 인상", "category": "경제"},
        )
        excluded = []
        rep = curate.pick_representative(
            cluster, lambda link, title="": "본문 " * 100,
            lambda t, b: {"total": 0.9}, {}, excluded,
            title_penalty_fn=lambda t: 8.0 if t.endswith("?") else 0.0)
        self.assertEqual(rep["link"], "y")
        self.assertTrue(any(e["reason"] == "clickbait" for e in excluded))

    def test_low_score_observed_not_excluded(self):
        # D4 관찰 모드: 본문 하한 미달은 로그만 남기고 배제하지 않는다(대표 될 수 있음).
        cluster = self._cluster(
            {"source": "A", "link": "x", "title": "T", "category": "경제"})
        excluded = []
        rep = curate.pick_representative(
            cluster, lambda link, title="": "본문 " * 100,
            lambda t, b: {"total": 0.2}, {}, excluded)   # 0.2 < 0.35 관찰선
        self.assertEqual(rep["link"], "x")               # 배제 안 됨
        self.assertTrue(any(e["reason"] == "low_score_observed" for e in excluded))


class SelectIntegrationTest(unittest.TestCase):
    def _art(self, title, source, link):
        return {"title": title, "source": source, "link": link, "category": "경제",
                "summary": "", "published_iso": "2026-07-15T09:00:00+09:00"}

    def test_min3_media_only_no_backfill(self):
        arts = [
            self._art("금리 동결 결정", "A", "c1"),   # 3매체 → 통과
            self._art("금리 동결 결정", "B", "c2"),
            self._art("금리 동결 결정", "C", "c3"),
            self._art("환율 급등 마감", "A", "s1"),   # 2매체 → 미달, 드롭
            self._art("환율 급등 마감", "B", "s2"),
            self._art("유가 하락 지속", "D", "solo"),  # 단독 → 드롭(백필 없음)
        ]
        raw = {"date": "2026-07-15", "articles": arts}
        today = datetime(2026, 7, 15, 12, tzinfo=KST)
        result = curate.select(
            raw, today, default_limit=10,
            extract_fn=lambda link, title="": "본문 " * 200,
            score_fn=lambda title, body: {"total": 0.9}, ranks={})
        econ = result["categories"]["경제"]
        self.assertEqual(len(econ), 1)                    # 3매체 사건 1건만(백필 없음)
        self.assertEqual(econ[0]["corroboration_count"], 3)
        self.assertNotIn("members", econ[0])              # 경량화
        # 통과 클러스터만 평판 통계 배출
        self.assertEqual(len(result["selection_stats"]), 1)
        self.assertEqual(set(result["selection_stats"][0]["members"]), {"A", "B", "C"})

    def test_length_filter_drops_member(self):
        arts = [
            self._art("금리 동결 결정", "A", "c1"),
            self._art("금리 동결 결정", "B", "c2"),
            self._art("금리 동결 결정", "C", "c3"),
        ]
        raw = {"date": "2026-07-15", "articles": arts}
        today = datetime(2026, 7, 15, 12, tzinfo=KST)
        bodies = {"c1": "짧", "c2": "본문 " * 200, "c3": "본문 " * 200}  # c1 길이 미달
        result = curate.select(
            raw, today, default_limit=10,
            extract_fn=lambda link, title="": bodies[link],
            score_fn=lambda title, body: {"total": 0.9}, ranks={})
        econ = result["categories"]["경제"]
        self.assertEqual(len(econ), 1)
        self.assertNotEqual(econ[0]["link"], "c1")        # c1 길이미달 → 대표 아님
        excluded_links = [e["link"] for e in result["gate_excluded"]]
        self.assertIn("c1", excluded_links)


if __name__ == "__main__":
    unittest.main()
