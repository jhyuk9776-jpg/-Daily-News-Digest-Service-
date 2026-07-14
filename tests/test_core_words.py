"""코어단어 추출·점수·주제·가중치 테스트 (네트워크/API 미사용)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import core_words  # noqa: E402


class ExtractTest(unittest.TestCase):
    def test_frequent_token_is_core(self):
        titles = ["코스피 3000 돌파", "코스피 강세 지속", "삼성전자 신제품"]
        core = core_words.extract_core_words(titles)
        self.assertIn("코스피", core)       # 2개 제목 등장
        self.assertNotIn("삼성전자", core)   # 1개 제목뿐
        self.assertNotIn("기자", core)       # 불용어

    def test_same_title_repeat_not_double_counted(self):
        # 한 제목에서 두 번 나와도 1회로(제목 단위 빈도)
        titles = ["코스피 코스피 코스피", "다른 뉴스"]
        self.assertNotIn("코스피", core_words.extract_core_words(titles))


class StatsTest(unittest.TestCase):
    def _articles(self):
        return [
            {"title": "코스피 3000", "source": "한국경제"},
            {"title": "코스피 강세", "source": "한국경제"},
            {"title": "코스피 마감", "source": "매일경제"},
            {"title": "환율 급등", "source": "SBS"},
        ]

    def test_score_formula(self):
        stats = core_words.core_word_stats(self._articles(), {"코스피"})
        s = stats["코스피"]
        self.assertEqual(s["media_count"], 2)      # 한국경제·매일경제
        self.assertEqual(s["article_count"], 3)
        self.assertAlmostEqual(s["score"], 2 + 3 * 0.2)  # 2.6

    def test_top_topics_ranked(self):
        arts = self._articles()
        stats = core_words.core_word_stats(arts, {"코스피", "환율"})
        top = core_words.top_topics(stats, n=3)
        self.assertEqual(top[0][0], "코스피")   # 점수 2.6 > 환율 1.2
        self.assertEqual(top[1][0], "환율")


class WeightTest(unittest.TestCase):
    def _store(self):
        return {"weights": {}, "processed_dates": []}

    def test_update_applies_rank_points(self):
        store = self._store()
        top3 = [("코스피", {}), ("환율", {}), ("금리", {})]
        core_words.update_core_weights(store, top3, "2026-07-15", alpha=0.1)
        self.assertAlmostEqual(store["weights"]["코스피"], 0.5)  # 5*0.1
        self.assertAlmostEqual(store["weights"]["환율"], 0.3)
        self.assertAlmostEqual(store["weights"]["금리"], 0.1)

    def test_weight_of_base_one(self):
        store = {"weights": {"코스피": 0.5}, "processed_dates": []}
        self.assertAlmostEqual(core_words.weight_of(store, "코스피"), 1.5)  # 1 + 0.5
        self.assertAlmostEqual(core_words.weight_of(store, "미등록"), 1.0)  # 기본 1

    def test_date_idempotent(self):
        store = self._store()
        core_words.update_core_weights(store, [("코스피", {})], "2026-07-15")
        core_words.update_core_weights(store, [("코스피", {})], "2026-07-15")
        self.assertAlmostEqual(store["weights"]["코스피"], 0.5)  # 한 번만

    def test_accumulates_across_dates(self):
        store = self._store()
        core_words.update_core_weights(store, [("코스피", {})], "2026-07-15")
        core_words.update_core_weights(store, [("코스피", {})], "2026-07-16")
        self.assertAlmostEqual(store["weights"]["코스피"], 1.0)  # 0.5 + 0.5


class RecordTopicsTest(unittest.TestCase):
    def test_writes_topics_file(self):
        import json
        import tempfile
        from pathlib import Path
        top3 = [("코스피", {"score": 2.6, "media_count": 2, "article_count": 3})]
        with tempfile.TemporaryDirectory() as d:
            core_words.record_topics("2026-07-15", top3, scores_dir=Path(d))
            data = json.loads((Path(d) / "topics-2026-07-15.json").read_text(encoding="utf-8"))
            self.assertEqual(data["topics"][0]["word"], "코스피")
            self.assertAlmostEqual(data["topics"][0]["score"], 2.6)


if __name__ == "__main__":
    unittest.main()
