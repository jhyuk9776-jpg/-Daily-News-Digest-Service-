"""collect_digest: 선별+요약결과 → 웹 계약(JSON) 구조 검증 (네트워크/API 미사용).

실행: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

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
                    "related_links": [{"source": "매일경제", "link": "L2", "extra": "버릴것"}],
                },
                {
                    "title": "제목B(요약실패)",
                    "link": "L3",
                    "source": "SBS",
                    "related_links": [],
                },
            ],
            "사회": [],
        },
    }


class CollectDigestTest(unittest.TestCase):
    def test_structure_and_fields(self):
        selected = _selected()
        results = {"L1": (["사실1", "사실2"], "ok")}  # L3는 실패라 없음

        digest = summarize.collect_digest(selected, results)

        self.assertEqual(digest["date"], "2026-07-07")
        names = [c["name"] for c in digest["categories"]]
        self.assertEqual(names, ["경제", "사회"])  # 분야 순서·빈 분야 보존

        econ = digest["categories"][0]
        self.assertEqual(len(econ["items"]), 1)  # 요약 성공 1건만
        item = econ["items"][0]
        self.assertEqual(item["title"], "제목A")
        self.assertEqual(item["bullets"], ["사실1", "사실2"])
        self.assertEqual(item["source"], "한국경제")
        self.assertEqual(item["link"], "L1")
        self.assertEqual(item["related_links"], [{"source": "매일경제", "link": "L2"}])

        self.assertEqual(digest["categories"][1]["items"], [])  # 사회 빈 분야


if __name__ == "__main__":
    unittest.main()
