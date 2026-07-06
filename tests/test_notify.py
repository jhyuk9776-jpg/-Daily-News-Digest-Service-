"""이메일 발송(notify)·제목표기(summarize) 검증 (표준 unittest, 네트워크/SMTP 미사용).

실행: python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import summarize  # noqa: E402
import notify  # noqa: E402


SAMPLE_MD = """# 오늘의 뉴스 요약 - 2026년 07월 06일 월요일

> 생성: 2026-07-06 06:00 KST · 요약실패 1건 · 호출오류 0건 · 추출실패 0건

## 경제

### 삼성 사내대출 제한
- 삼성전자가 사내 주택대출을 제한
- 출처: [한국경제](https://www.hankyung.com/article/1) 외 관련 1건

## IT/테크

### 양자컴퓨터 암호
- 큐비트 통념이 깨졌다
- 출처: [전자신문](https://www.etnews.com/2)
"""


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


class ParseDigestTest(unittest.TestCase):
    def setUp(self):
        self.d = notify.parse_digest(SAMPLE_MD)

    def test_title_and_meta(self):
        self.assertEqual(
            self.d["title_line"], "오늘의 뉴스 요약 - 2026년 07월 06일 월요일"
        )
        self.assertIn("요약실패 1건", self.d["meta"])

    def test_categories_and_count(self):
        self.assertEqual([c["name"] for c in self.d["categories"]], ["경제", "IT/테크"])
        self.assertEqual(self.d["total_count"], 2)

    def test_article_bullets_and_source(self):
        art = self.d["categories"][0]["articles"][0]
        self.assertEqual(art["title"], "삼성 사내대출 제한")
        self.assertEqual(art["bullets"], ["삼성전자가 사내 주택대출을 제한"])
        self.assertEqual(art["source"]["label"], "한국경제")
        self.assertEqual(art["source"]["url"], "https://www.hankyung.com/article/1")
        self.assertEqual(art["source"]["extra"], "외 관련 1건")

    def test_source_without_extra(self):
        art = self.d["categories"][1]["articles"][0]
        self.assertEqual(art["source"]["extra"], "")


class RenderEmailTest(unittest.TestCase):
    def setUp(self):
        digest = notify.parse_digest(SAMPLE_MD)
        self.subject, self.html, self.text = notify.render_email(digest)

    def test_subject(self):
        self.assertEqual(
            self.subject, "📰 오늘의 뉴스 요약 - 2026년 07월 06일 월요일 (2건)"
        )

    def test_text_is_kakao_plain(self):
        self.assertIn("▪ 삼성 사내대출 제한", self.text)
        self.assertIn("──────── 경제 ────────", self.text)
        self.assertIn("https://www.hankyung.com/article/1", self.text)
        self.assertNotIn("](", self.text)  # 마크다운 링크 문법 없음
        self.assertIn("요약실패 1건", self.text)

    def test_html_has_links_and_kakao_block(self):
        self.assertIn('<a href="https://www.etnews.com/2">전자신문</a>', self.html)
        self.assertIn("<h2>경제</h2>", self.html)
        self.assertIn("카카오톡용", self.html)
        self.assertIn("<pre>", self.html)
