"""feedparser 내장 HTTP 경로가 깨지는 피드(예: 한국경제 gzip)를 바이트 직접수신으로
구제하는 폴백 검증 (네트워크 미사용, feedparser·urllib mock)."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import fetch  # noqa: E402


class FetchGzipFallbackTest(unittest.TestCase):
    def _ok(self, entry):
        return SimpleNamespace(bozo=0, entries=[entry])

    def _broken(self):
        return SimpleNamespace(bozo=1, entries=[],
                               get=lambda k, d=None: "not well-formed")

    def test_bozo_no_entries_refetches_bytes(self):
        """1차 파싱이 bozo·엔트리0이면 바이트를 직접 받아 재파싱해 구제한다."""
        entry = {"title": "제목", "link": "http://x/1", "published": "",
                 "summary": "요약", "author": ""}
        with patch("fetch.feedparser.parse",
                   side_effect=[self._broken(), self._ok(entry)]) as parse, \
             patch("fetch._fetch_bytes", return_value=b"<rss/>") as fb:
            arts = fetch.fetch_feed("경제", {"매체명": "한국경제", "url": "u"}, "now")
        self.assertEqual(len(arts), 1)
        self.assertEqual(arts[0]["title"], "제목")
        fb.assert_called_once_with("u")
        self.assertEqual(parse.call_count, 2)

    def test_healthy_feed_does_not_refetch(self):
        """1차 파싱이 정상이면 바이트 재수신을 하지 않는다(정상 피드 경로 불변)."""
        entry = {"title": "제목", "link": "http://x/2", "published": "", "summary": ""}
        with patch("fetch.feedparser.parse", return_value=self._ok(entry)), \
             patch("fetch._fetch_bytes") as fb:
            arts = fetch.fetch_feed("경제", {"매체명": "연합뉴스", "url": "u"}, "now")
        self.assertEqual(len(arts), 1)
        fb.assert_not_called()

    def test_still_raises_when_fallback_also_empty(self):
        """폴백도 실패하면 예외를 올린다."""
        with patch("fetch.feedparser.parse",
                   side_effect=[self._broken(), self._broken()]), \
             patch("fetch._fetch_bytes", return_value=b"garbage"):
            with self.assertRaises(RuntimeError):
                fetch.fetch_feed("경제", {"매체명": "한국경제", "url": "u"}, "now")


if __name__ == "__main__":
    unittest.main()
