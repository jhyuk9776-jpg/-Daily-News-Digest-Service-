"""대표 선정(길이필터+채점) + 선택률 순위 tie-break 테스트(주입식, 네트워크 없음)."""

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
        # x는 길이 이탈로 기록, y는 통과 후보 점수 관찰로 기록(분포 수집)
        by_link = {e["link"]: e for e in excluded}
        self.assertTrue(by_link["x"]["reason"].startswith("length"))
        self.assertEqual(by_link["y"]["reason"], "score_observed")

    def test_tie_broken_by_selection_rank(self):
        cluster = self._cluster(
            {"source": "A", "link": "x", "title": "T", "category": "경제"},
            {"source": "B", "link": "y", "title": "T", "category": "경제"},
        )
        body = "본문 " * 200  # 유효 길이
        ranks = {"A": 2, "B": 1}  # B가 우선(선택률 순위 낮음=상위)
        rep = curate.pick_representative(
            cluster, lambda link, title="": body,
            lambda title, b: {"total": 0.5}, ranks, [])
        self.assertEqual(rep["source"], "B")        # 동점 → 선택률 순위 우선

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

    def test_low_score_excluded(self):
        # 하드 하한(2026-07-22 승격): 본문 점수 < REP_SCORE_FLOOR면 대표 자격 박탈.
        cluster = self._cluster(
            {"source": "A", "link": "x", "title": "T", "category": "경제"})
        excluded = []
        rep = curate.pick_representative(
            cluster, lambda link, title="": "본문 " * 100,
            lambda t, b: {"total": 0.2}, {}, excluded)   # 0.2 < 0.45 하한
        self.assertIsNone(rep)                            # 유일 멤버 배제 → 클러스터 탈락
        self.assertTrue(any(e["reason"] == "low_score" for e in excluded))


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
