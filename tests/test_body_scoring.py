"""본문 객관성·풍부함 결합 채점 테스트 (Phase 0–1, 네트워크/API 미사용)."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import objectivity  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


class BodyObjectivityTest(unittest.TestCase):
    def test_title_only_rules_do_not_leak_to_body(self):
        # '?$'·추측형 종결은 scope:title. 본문에 물음표 문장이 있어도 감점 없어야 한다.
        body = "정부는 물가가 오를까? 라는 질문에 답했다. " * 3
        r = objectivity.body_objectivity(body)
        self.assertEqual(r["hits"], [])
        self.assertEqual(r["score"], 100)


if __name__ == "__main__":
    unittest.main()
