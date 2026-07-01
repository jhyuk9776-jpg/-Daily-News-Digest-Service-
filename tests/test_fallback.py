"""요약 폴백 체인 검증 (표준 unittest, 네트워크/API 미사용).

동작 사양(기획/04-decision-log 1.2 확장, 2026-07-01 결정):
  - 우선순위 순 후보(대표 매체 RSS/본문 → 다음 순위 매체 본문)를 돈다.
  - 어떤 후보에서 불릿이 나오면 즉시 그걸 쓴다(뒤 후보는 시도 안 함).
  - 모든 후보에서 불릿이 0개면 요약 생략(api_failed) → 1순위 링크만 남긴다.
  - 후보 텍스트를 하나도 못 만들면 extract_failed.

실행: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import summarize  # noqa: E402


def _item():
    return {
        "title": "제목",
        "source": "매일경제",
        "link": "L1",
        "summary": "짧은요약",
        "related_links": [{"source": "연합", "link": "L2"}],
    }


class SummarizeItemTest(unittest.TestCase):
    @patch("summarize.summarize_one")
    @patch("summarize.iter_contents")
    def test_escalates_to_next_candidate_on_empty_bullets(self, m_iter, m_sum):
        m_iter.return_value = iter([
            {"text": "rss", "content_source": "매일경제", "method": "rss", "link": "L1"},
            {"text": "body", "content_source": "매일경제", "method": "body", "link": "L1"},
        ])
        m_sum.side_effect = [[], ["사실"]]  # 첫 후보 불릿 0 → 다음 후보에서 성공
        bullets, source, status, cached = summarize.summarize_item(_item(), {}, False)
        self.assertEqual(bullets, ["사실"])
        self.assertEqual(status, "ok")
        self.assertEqual(m_sum.call_count, 2)

    @patch("summarize.summarize_one")
    @patch("summarize.iter_contents")
    def test_all_candidates_empty_returns_api_failed(self, m_iter, m_sum):
        m_iter.return_value = iter([
            {"text": "a", "content_source": "매일경제", "method": "rss", "link": "L1"},
            {"text": "b", "content_source": "연합", "method": "body", "link": "L2"},
        ])
        m_sum.side_effect = [[], []]
        bullets, source, status, cached = summarize.summarize_item(_item(), {}, False)
        self.assertEqual(bullets, [])
        self.assertEqual(status, "api_failed")

    @patch("summarize.summarize_one")
    @patch("summarize.iter_contents")
    def test_no_content_candidate_returns_extract_failed(self, m_iter, m_sum):
        m_iter.return_value = iter([])
        bullets, source, status, cached = summarize.summarize_item(_item(), {}, False)
        self.assertEqual(status, "extract_failed")
        m_sum.assert_not_called()

    @patch("summarize.summarize_one")
    @patch("summarize.iter_contents")
    def test_first_success_stops_early(self, m_iter, m_sum):
        m_iter.return_value = iter([
            {"text": "a", "content_source": "매일경제", "method": "rss", "link": "L1"},
            {"text": "b", "content_source": "연합", "method": "body", "link": "L2"},
        ])
        m_sum.side_effect = [["사실"]]
        bullets, source, status, cached = summarize.summarize_item(_item(), {}, False)
        self.assertEqual(m_sum.call_count, 1)
        self.assertEqual(status, "ok")

    @patch("summarize.summarize_one")
    @patch("summarize.iter_contents")
    def test_cache_hit_skips_api(self, m_iter, m_sum):
        m_iter.return_value = iter([
            {"text": "a", "content_source": "매일경제", "method": "rss", "link": "L1"},
        ])
        cache = {"L1": ["캐시된 사실"]}
        bullets, source, status, cached = summarize.summarize_item(_item(), cache, False)
        self.assertEqual(bullets, ["캐시된 사실"])
        self.assertTrue(cached)
        m_sum.assert_not_called()

    @patch("summarize.summarize_one")
    @patch("summarize.iter_contents")
    def test_api_error_falls_through_to_next_candidate(self, m_iter, m_sum):
        m_iter.return_value = iter([
            {"text": "a", "content_source": "매일경제", "method": "rss", "link": "L1"},
            {"text": "b", "content_source": "연합", "method": "body", "link": "L2"},
        ])
        m_sum.side_effect = [RuntimeError("429"), ["사실"]]
        bullets, source, status, cached = summarize.summarize_item(_item(), {}, False)
        self.assertEqual(bullets, ["사실"])
        self.assertEqual(status, "ok")


if __name__ == "__main__":
    unittest.main()
