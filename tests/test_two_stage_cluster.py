"""2단계 클러스터링(매체 내부→매체 간) + 코어단어 가산 병합 테스트."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import curate  # noqa: E402

KST = timezone(timedelta(hours=9))


def _art(title, source, link, iso):
    return {"title": title, "source": source, "link": link,
            "category": "경제", "summary": "", "published_iso": iso}


class TwoStageClusterTest(unittest.TestCase):
    def test_intra_media_collapse_keeps_newest(self):
        arts = [
            _art("코스피 3000 돌파", "한국경제", "a", "2026-07-15T09:00:00+09:00"),
            _art("코스피 3000 돌파 마감", "한국경제", "b", "2026-07-15T10:00:00+09:00"),
        ]
        clusters = curate.cluster_articles(arts, core_words={"코스피"})
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["link"], "b")              # 최근 1건
        self.assertEqual(clusters[0]["article_total"], 2)       # 붕괴 전 총 기사 수
        self.assertEqual(clusters[0]["corroboration_count"], 1)  # 같은 매체

    def test_cross_media_corroboration(self):
        arts = [
            _art("금리 동결 결정", "한국경제", "a", "2026-07-15T09:00:00+09:00"),
            _art("금리 동결 결정", "연합뉴스", "b", "2026-07-15T09:10:00+09:00"),
        ]
        clusters = curate.cluster_articles(arts, core_words=set())
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["corroboration_count"], 2)
        self.assertEqual({m["source"] for m in clusters[0]["members"]},
                         {"한국경제", "연합뉴스"})

    def test_core_word_bonus_tips_merge(self):
        a = ("삼성전자 반도체 호황", frozenset({"삼성전자"}))
        b = ("삼성전자 신공장 착공", frozenset({"삼성전자"}))
        r_no = SequenceMatcher(None, a[0], b[0]).ratio()
        # 코어단어 1개 공유 → +0.15 가산
        self.assertAlmostEqual(curate._effective_ratio(a, b), r_no + 0.15)

    def test_distinct_topics_not_merged(self):
        arts = [
            _art("금리 동결", "한국경제", "a", "2026-07-15T09:00:00+09:00"),
            _art("환율 급등", "한국경제", "b", "2026-07-15T09:00:00+09:00"),
        ]
        clusters = curate.cluster_articles(arts, core_words=set())
        self.assertEqual(len(clusters), 2)


class SortTest(unittest.TestCase):
    def test_higher_core_weight_ranks_first(self):
        iso = "2026-07-15T09:00:00+09:00"
        arts = [
            _art("코스피 강세 지속", "한국경제", "a", iso),
            _art("코스피 강세 지속", "연합뉴스", "a2", iso),
            _art("금리 인하 전망", "SBS", "b", iso),
            _art("금리 인하 전망", "매일경제", "b2", iso),
        ]
        raw = {"date": "2026-07-15", "articles": arts}
        today = datetime(2026, 7, 15, 12, tzinfo=KST)
        # 둘 다 교차검증 2·코어단어 있음 → 가중치 합으로 결정. 코스피>금리
        weights = {"weights": {"코스피": 1.0, "금리": 0.0}, "processed_dates": []}
        result = curate.select(raw, {}, today, default_limit=10, core_weights=weights)
        econ = result["categories"]["경제"]
        self.assertEqual(len(econ), 2)
        self.assertIn("코스피", econ[0]["core_words"])   # 가중치 높은 코스피 먼저


if __name__ == "__main__":
    unittest.main()
