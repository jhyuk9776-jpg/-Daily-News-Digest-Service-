"""블랙리스트 기자 기사가 선별 후보에서 제외되는지 검증 (네트워크/API 미사용)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import curate  # noqa: E402


def _art(source, author):
    return {"category": "경제", "source": source, "author": author,
            "title": f"{source}-{author}", "summary": "", "link": f"L-{source}-{author}",
            "published_iso": "2026-07-08T01:00:00+00:00"}


class FilterBlacklistedTest(unittest.TestCase):
    def test_blacklisted_reporter_removed(self):
        arts = [_art("연합뉴스", "황철환 기자"), _art("연합뉴스", "김리안")]
        blacklist = {"연합뉴스::황철환"}
        out = curate.filter_blacklisted(arts, blacklist)
        self.assertEqual([a["author"] for a in out], ["김리안"])

    def test_empty_blacklist_keeps_all(self):
        arts = [_art("연합뉴스", "황철환 기자")]
        self.assertEqual(curate.filter_blacklisted(arts, set()), arts)

    def test_article_without_author_passes(self):
        art = {"category": "경제", "source": "연합뉴스", "title": "무저자",
               "summary": "", "link": "L", "published_iso": ""}
        out = curate.filter_blacklisted([art], {"연합뉴스::황철환"})
        self.assertEqual(out, [art])

    def test_same_name_other_source_not_filtered(self):
        arts = [_art("한국경제", "황철환 기자")]  # 블랙은 연합뉴스::황철환뿐
        out = curate.filter_blacklisted(arts, {"연합뉴스::황철환"})
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
