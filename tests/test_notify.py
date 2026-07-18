"""이메일 발송(notify)·제목표기(summarize) 검증 (표준 unittest, 네트워크/SMTP 미사용).

실행: python3 -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

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
        # 카톡용은 출처명만 남기고 링크(URL)는 뺀다(복붙 시 지저분한 URL 방지).
        self.assertIn("출처: 한국경제", self.text)
        self.assertNotIn("https://www.hankyung.com/article/1", self.text)
        self.assertNotIn("http", self.text)  # plain 블록에 URL 없음
        self.assertNotIn("](", self.text)  # 마크다운 링크 문법 없음
        self.assertIn("요약실패 1건", self.text)

    def test_html_has_links_no_kakao_block(self):
        self.assertIn('<a href="https://www.etnews.com/2">전자신문</a>', self.html)
        self.assertIn("<h2>경제</h2>", self.html)
        self.assertNotIn("카카오톡용", self.html)
        self.assertNotIn("<pre>", self.html)


class SendEmailTest(unittest.TestCase):
    @patch("notify.smtplib.SMTP_SSL")
    def test_login_and_send(self, mock_ssl):
        server = MagicMock()
        mock_ssl.return_value.__enter__.return_value = server
        notify.send_email("제목", "<html>h</html>", "plain text", "me@gmail.com", "pw16")
        mock_ssl.assert_called_once_with("smtp.gmail.com", 465)
        server.login.assert_called_once_with("me@gmail.com", "pw16")
        server.send_message.assert_called_once()
        msg = server.send_message.call_args[0][0]
        self.assertEqual(msg["To"], "me@gmail.com")  # to 미지정 → 발신주소
        self.assertEqual(msg["Subject"], "제목")
        self.assertEqual(len(msg.get_payload()), 2)  # plain + html
        self.assertEqual(msg.get_payload()[0].get_content_type(), "text/plain")
        self.assertEqual(msg.get_payload()[1].get_content_type(), "text/html")

    @patch("notify.smtplib.SMTP_SSL")
    def test_to_override(self, mock_ssl):
        server = MagicMock()
        mock_ssl.return_value.__enter__.return_value = server
        notify.send_email("s", "h", "t", "me@gmail.com", "pw", to="other@x.com")
        msg = server.send_message.call_args[0][0]
        self.assertEqual(msg["To"], "other@x.com")


class MainTest(unittest.TestCase):
    def _write_today(self, tmp):
        date = datetime.now(notify.KST).strftime("%Y-%m-%d")
        (Path(tmp) / f"{date}.md").write_text(SAMPLE_MD, encoding="utf-8")

    def test_skip_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(notify, "NEWS_DIR", Path(tmp)):
                self.assertEqual(notify.main(), 0)

    def test_missing_env_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_today(tmp)
            with patch.object(notify, "NEWS_DIR", Path(tmp)), patch.dict(
                os.environ, {}, clear=True
            ):
                self.assertEqual(notify.main(), 1)

    def test_success_sends_and_returns_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_today(tmp)
            env = {"GMAIL_ADDRESS": "me@gmail.com", "GMAIL_APP_PASSWORD": "pw"}
            with patch.object(notify, "NEWS_DIR", Path(tmp)), patch.dict(
                os.environ, env, clear=True
            ), patch.object(notify, "send_email") as mock_send:
                self.assertEqual(notify.main(), 0)
                mock_send.assert_called_once()
