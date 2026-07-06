"""이메일 발송(notify)·제목표기(summarize) 검증 (표준 unittest, 네트워크/SMTP 미사용).

실행: python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import summarize  # noqa: E402


class KoreanDateTest(unittest.TestCase):
    def test_monday(self):
        self.assertEqual(summarize.korean_date("2026-07-06"), "2026년 07월 06일 월요일")

    def test_sunday(self):
        self.assertEqual(summarize.korean_date("2026-07-05"), "2026년 07월 05일 일요일")


class BuildMarkdownTitleTest(unittest.TestCase):
    def test_h1_uses_new_title_and_korean_date(self):
        selected = {"date": "2026-07-06", "categories": {}}
        counters = {"api_failed": 0, "call_error": 0, "extract_failed": 0}
        md = summarize.build_markdown(selected, {}, counters)
        self.assertEqual(
            md.splitlines()[0], "# 오늘의 뉴스 요약 - 2026년 07월 06일 월요일"
        )
