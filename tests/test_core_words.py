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


if __name__ == "__main__":
    unittest.main()
