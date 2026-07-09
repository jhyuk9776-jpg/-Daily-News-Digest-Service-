"""파이프라인 JSON 출력 계약 검증 (네트워크/API 미사용, dry_run).

실행: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import summarize  # noqa: E402


def _selected():
    return {
        "date": "2026-07-07",
        "categories": {
            "경제": [
                {
                    "title": "제목A",
                    "link": "L1",
                    "source": "한국경제",
                    "related_links": [{"source": "매일경제", "link": "L2"}],
                }
            ],
            "사회": [],
        },
    }


class DigestJsonTest(unittest.TestCase):
    def test_run_writes_contract_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            web_data = tmp / "web" / "public" / "data"

            def fake_summarize_item(item, cache, dry_run, body_cache=None):
                # (bullets, source, status, cached, detail)
                return (["사실1", "사실2"], item["source"], "ok", False, None)

            with patch.object(summarize, "NEWS_DIR", tmp / "News"), \
                 patch.object(summarize, "WEB_DATA_DIR", web_data), \
                 patch.object(summarize, "load_selected", lambda date: _selected()), \
                 patch.object(summarize, "save_failure_log", lambda *a, **k: tmp / "f.json"), \
                 patch.object(summarize, "summarize_item", fake_summarize_item):
                summarize.run("2026-07-07", dry_run=True)

            dated = web_data / "2026-07-07.json"
            latest = web_data / "latest.json"
            self.assertTrue(dated.exists())
            self.assertTrue(latest.exists())

            data = json.loads(dated.read_text(encoding="utf-8"))
            self.assertEqual(data["date"], "2026-07-07")
            self.assertEqual([c["name"] for c in data["categories"]], ["경제", "사회"])
            item = data["categories"][0]["items"][0]
            self.assertEqual(item["title"], "제목A")
            self.assertEqual(item["bullets"], ["사실1", "사실2"])
            self.assertEqual(item["related_links"], [{"source": "매일경제", "link": "L2"}])
            # latest는 dated와 동일 내용
            self.assertEqual(latest.read_text(encoding="utf-8"),
                             dated.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
