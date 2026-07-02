"""분야별 요약 상한(Phase 1.5) 테스트 (표준 unittest, 네트워크/API 미사용)."""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import curate  # noqa: E402


class LoadLimitsTest(unittest.TestCase):
    def test_parses_default_and_per_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "limits.yaml"
            p.write_text("default: 2\nper_category:\n  경제: 10\n", encoding="utf-8")
            default, per_cat = curate.load_limits(p)
        self.assertEqual(default, 2)
        self.assertEqual(per_cat, {"경제": 10})

    def test_missing_file_falls_back(self):
        default, per_cat = curate.load_limits(Path("/nonexistent/limits.yaml"))
        self.assertEqual(default, 2)
        self.assertEqual(per_cat, {})


if __name__ == "__main__":
    unittest.main()
