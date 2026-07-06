"""본문 추출 정확도 검증 (표준 unittest, 네트워크 미사용).

실행: python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import extract  # noqa: E402

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
