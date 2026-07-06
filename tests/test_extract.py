"""본문 추출 정확도 검증 (표준 unittest, 네트워크 미사용).

실행: python3 -m unittest discover -s tests
"""
import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import extract  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

_LONG = "가" * 100  # MIN_BODY(80) 이상 확보용


class LooksLikeBodyTest(unittest.TestCase):
    def test_real_body_with_title_keyword_passes(self):
        text = "세계 식량가격지수가 전월 대비 0.8% 하락했다. " + _LONG
        self.assertTrue(extract.looks_like_body(text, "세계 식량가격지수 하락"))

    def test_too_short_fails(self):
        self.assertFalse(extract.looks_like_body("짧은 본문", "제목"))

    def test_recommendation_list_many_dates_fails(self):
        # 추천 위젯: 여러 기사 티저 + 각 날짜 → 날짜 3개 이상
        text = ("올영 기사 A 2026.07.05 올영 기사 B 2026.06.22 "
                "올영 기사 C 2026.06.11 " + _LONG)
        # 제목 키워드('올영')가 본문에 있어도 날짜 신호로 기각돼야 한다
        self.assertFalse(extract.looks_like_body(text, "올영 제주도민 설움 덜었다"))

    def test_title_unrelated_body_fails(self):
        text = "전혀 다른 주제의 긴 본문입니다. " + _LONG
        self.assertFalse(extract.looks_like_body(text, "식량가격지수 하락"))

    def test_no_title_skips_relevance(self):
        text = "제목 없이 들어온 충분히 긴 본문입니다. " + _LONG
        self.assertTrue(extract.looks_like_body(text, ""))


class ParseBodyTest(unittest.TestCase):
    def setUp(self):
        self.html = (FIXTURES / "hankyung_food.html").read_text(encoding="utf-8")
        self.url = "https://www.hankyung.com/article/2026070455227"

    def test_extracts_real_body_not_recommendation(self):
        body = extract._parse_body(self.html, self.url, title="세계 식량가격지수 2개월 연속 하락")
        self.assertIsNotNone(body)
        # 진짜 본문 신호: 제목 키워드 + 원문 수치가 살아 있음
        self.assertIn("식량가격지수", body)
        self.assertIn("130.3", body)   # ISSUE-002: 본문 수치 보존 확인
        # 추천위젯/저작권 상투구가 본문을 지배하지 않음
        self.assertNotIn("무단전재", body)

    def test_domain_helper(self):
        self.assertEqual(extract._domain("https://www.hankyung.com/article/1"), "hankyung.com")
        self.assertEqual(extract._domain("https://news.sbs.co.kr/x"), "news.sbs.co.kr")
