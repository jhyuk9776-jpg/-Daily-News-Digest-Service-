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


KST = timezone(timedelta(hours=9))

# 서로 유사도 0.6 미만이 되도록 겹치지 않는 제목들(클러스터가 각각 분리되게).
ECON_TITLES = [
    "무역흑자", "금리동결", "반도체수출", "부동산대책", "환율급등", "국채발행",
    "소비자물가", "고용지표", "코스피상승", "유가하락", "세수부족", "가계부채",
]
SOCIAL_TITLES = ["학교폭력", "교통사고", "의료파업"]


def _art(category, source, title, iso):
    return {"category": category, "source": source, "title": title,
            "summary": "", "link": f"L-{title}", "published_iso": iso}


class SelectLimitTest(unittest.TestCase):
    def _raw(self):
        iso = "2026-07-02T01:00:00+00:00"
        arts = [_art("경제", "한국경제", t, iso) for t in ECON_TITLES]
        arts += [_art("사회", "경향신문", t, iso) for t in SOCIAL_TITLES]
        return {"date": "2026-07-02", "articles": arts}

    def _today(self):
        return datetime(2026, 7, 2, 12, 0, tzinfo=KST)

    def test_per_category_cap_applied(self):
        # 경제 후보 12개 + 상한 10 → 경제 10개, 사회는 default 2
        result = curate.select(self._raw(), self._today(),
                               default_limit=2, per_category_limits={"경제": 10})
        self.assertEqual(len(result["categories"]["경제"]), 10)
        self.assertEqual(len(result["categories"]["사회"]), 2)

    def test_fewer_candidates_than_cap(self):
        # 경제 후보 12개인데 상한 20 → 있는 12개만(빈 채움 없음)
        result = curate.select(self._raw(), self._today(),
                               default_limit=2, per_category_limits={"경제": 20})
        self.assertEqual(len(result["categories"]["경제"]), 12)

    def test_default_when_no_config(self):
        # per_category_limits 미지정 → 모든 분야 default 2
        result = curate.select(self._raw(), self._today())
        self.assertEqual(len(result["categories"]["경제"]), 2)
        self.assertEqual(len(result["categories"]["사회"]), 2)


if __name__ == "__main__":
    unittest.main()
