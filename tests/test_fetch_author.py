"""fetch가 RSS author를 raw 기사에 저장하는지 검증 (네트워크 미사용, feedparser mock)."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import fetch  # noqa: E402


class FetchAuthorTest(unittest.TestCase):
    def _parsed(self, entry):
        return SimpleNamespace(bozo=0, entries=[entry])

    def test_author_is_captured(self):
        entry = {"title": "제목", "link": "http://x/1", "published": "",
                 "summary": "요약", "author": "황철환 기자"}
        with patch("fetch.feedparser.parse", return_value=self._parsed(entry)):
            arts = fetch.fetch_feed("경제", {"매체명": "연합뉴스", "url": "u"}, "now")
        self.assertEqual(arts[0]["author"], "황철환 기자")

    def test_missing_author_is_empty_string(self):
        entry = {"title": "제목", "link": "http://x/2", "published": "",
                 "summary": "요약"}
        with patch("fetch.feedparser.parse", return_value=self._parsed(entry)):
            arts = fetch.fetch_feed("경제", {"매체명": "연합뉴스", "url": "u"}, "now")
        self.assertEqual(arts[0]["author"], "")


if __name__ == "__main__":
    unittest.main()
