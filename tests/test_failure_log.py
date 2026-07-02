"""실패 로그 저장 테스트 (표준 unittest, 네트워크/API 미사용)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import failure_log  # noqa: E402


class SaveFailureLogTest(unittest.TestCase):
    def _failures(self):
        return [{"category": "경제", "source": "한국경제", "title": "칼럼",
                 "link": "L1", "reason": "api_failed", "detail": "모든 후보 불릿 0"}]

    def test_writes_file_with_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(failure_log, "FAILURES_DIR", Path(tmp)):
                path = failure_log.save_failure_log("2026-07-01", 16, self._failures())
                data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(data["date"], "2026-07-01")
        self.assertEqual(data["total_articles"], 16)
        self.assertEqual(data["failed_count"], 1)
        self.assertEqual(data["failures"][0]["reason"], "api_failed")
        self.assertIn("generated_at", data)

    def test_no_failures_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(failure_log, "FAILURES_DIR", Path(tmp)):
                result = failure_log.save_failure_log("2026-07-01", 16, [])
                files = list(Path(tmp).glob("*.json"))
        self.assertIsNone(result)
        self.assertEqual(files, [])


if __name__ == "__main__":
    unittest.main()
