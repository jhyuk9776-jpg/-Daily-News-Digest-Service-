"""run()이 대표 기사 본문을 판정해 기자 스트라이크를 기록하는지 검증."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import reporters  # noqa: E402
import summarize  # noqa: E402


class ReporterStrikeInRunTest(unittest.TestCase):
    def _selected(self):
        return {"date": "2026-07-08", "categories": {"경제": [
            {"title": "제목", "source": "연합뉴스", "author": "황철환 기자",
             "link": "L1", "related_links": []},
        ]}}

    def _run(self, tmp, extract_return):
        # summarize_item은 ok를 반환하도록 mock(요약 자체는 관심사 아님).
        with patch.dict(os.environ, {"REPLICATE_API_TOKEN": "x"}), \
             patch("summarize.load_selected", return_value=self._selected()), \
             patch("summarize.load_cache", return_value={}), \
             patch("summarize.save_cache"), \
             patch("summarize.save_failure_log"), \
             patch("summarize.summarize_item",
                   return_value=(["사실"], "연합뉴스", "ok", False, None)), \
             patch("summarize.extract_body", return_value=extract_return), \
             patch.object(summarize, "NEWS_DIR", Path(tmp)), \
             patch.object(summarize, "WEB_DATA_DIR", Path(tmp) / "web"), \
             patch.object(reporters, "REPORTERS_FILE", Path(tmp) / "reporters.json"):
            summarize.run("2026-07-08", dry_run=False)
            return reporters.load()

    def test_empty_body_records_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._run(tmp, None)  # extract_body None → empty
        self.assertEqual(data["연합뉴스::황철환"]["points"], 1)

    def test_sparse_body_records_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._run(tmp, "가" * 100)  # 100자 < 200 → sparse
        rec = data["연합뉴스::황철환"]
        self.assertEqual(rec["sparse_count"], 1)
        self.assertEqual(rec["points"], 0)

    def test_normal_body_records_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._run(tmp, "가" * 300)  # ≥200 → ok, 기록 없음
        self.assertEqual(data, {})  # 저장 파일 없음 → load() = {}


if __name__ == "__main__":
    unittest.main()
