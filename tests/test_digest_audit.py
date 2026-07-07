"""트랙2 다이제스트 본문 감사 테스트(네트워크 미사용, 본문 추출은 주입)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import digest_audit  # noqa: E402


class AuditDigestTest(unittest.TestCase):
    def _write_selected(self, d, date):
        payload = {"date": date, "categories": {
            "경제": [{"title": "무역흑자 361억달러", "summary": "", "link": "L1", "source": "한국경제"}],
            "사회": [{"title": "구조 소식", "summary": "", "link": "L2", "source": "경향신문"}],
        }}
        (Path(d) / f"{date}.json").write_text(json.dumps(payload, ensure_ascii=False))

    def test_body_hit_is_scored_and_reported(self):
        bodies = {"L1": "여기저기 아우성이 커지고 있다", "L2": "차분한 사실 보도"}
        with tempfile.TemporaryDirectory() as tmp:
            sel = Path(tmp) / "selected"; sel.mkdir()
            sc = Path(tmp) / "scores"; sc.mkdir()
            self._write_selected(sel, "2026-07-01")
            result = digest_audit.audit_digest(
                "2026-07-01", fetch_body=lambda u: bodies.get(u, ""),
                selected_dir=sel, scores_dir=sc)
            # L1은 본문에 '아우성'(medium 8 × body_factor 0.5 = 4) → 감점
            self.assertEqual(result["audited"], 2)
            self.assertEqual(result["penalized_count"], 1)
            saved = json.loads((sc / "digest-audit-2026-07-01.json").read_text())
            self.assertEqual(saved["items"][0]["link"], "L1")

    def test_missing_body_falls_back_to_title_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            sel = Path(tmp) / "selected"; sel.mkdir()
            sc = Path(tmp) / "scores"; sc.mkdir()
            self._write_selected(sel, "2026-07-01")
            result = digest_audit.audit_digest(
                "2026-07-01", fetch_body=lambda u: "",   # 본문 없음
                selected_dir=sel, scores_dir=sc)
        self.assertEqual(result["audited"], 2)
        self.assertEqual(result["penalized_count"], 0)   # 제목·리드 깨끗


if __name__ == "__main__":
    unittest.main()
