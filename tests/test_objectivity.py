"""매체 객관성 점수 축적기 테스트 (표준 unittest, 네트워크/API 미사용)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import objectivity  # noqa: E402


class ScoreTest(unittest.TestCase):
    def test_clean_title_is_baseline(self):
        art = {"title": "6월 무역수지 361억달러 흑자", "summary": ""}
        r = objectivity.objectivity_score(art)
        self.assertEqual(r["score"], 100)
        self.assertEqual(r["hits"], [])

    def test_phrase_penalized(self):
        art = {"title": "논란이 커지고 있다는 지적", "summary": ""}
        r = objectivity.objectivity_score(art)
        self.assertEqual(r["score"], 90)
        self.assertIn("논란이 커지고 있다", r["hits"])

    def test_multiple_hits_stack(self):
        art = {"title": "충격을 주고 있다", "summary": "큰 파장이 예상된다"}
        r = objectivity.objectivity_score(art)
        self.assertEqual(r["score"], 80)
        self.assertEqual(len(r["hits"]), 2)

    def test_pattern_match(self):
        art = {"title": "정부가 다 했네", "summary": ""}
        r = objectivity.objectivity_score(art)
        self.assertLess(r["score"], 100)
        self.assertTrue(r["hits"])

    def test_floor_clamp(self):
        # 감점이 아무리 쌓여도 FLOOR(0) 미만으로 내려가지 않는다.
        text = "논란이 커지고 있다 " * 20
        art = {"title": text, "summary": ""}
        r = objectivity.objectivity_score(art)
        self.assertEqual(r["score"], 0)


class MediaAggregateTest(unittest.TestCase):
    def _empty_store(self):
        return {"media": {}, "processed_dates": []}

    def test_new_media_uses_day_average_as_initial(self):
        arts = [
            {"title": "깨끗한 기사", "summary": "", "source": "한국경제"},
            {"title": "논란이 커지고 있다", "summary": "", "source": "한국경제"},
        ]  # 점수 100, 90 → 그날 평균 95
        store = objectivity.update_media_scores(self._empty_store(), arts, "2026-07-01")
        m = store["media"]["한국경제"]
        self.assertAlmostEqual(m["score"], 95.0)
        self.assertEqual(m["count"], 2)
        self.assertEqual(m["penalized"], 1)
        self.assertEqual(m["last_seen"], "2026-07-01")

    def test_ewma_blends_with_existing(self):
        store = {
            "media": {"한국경제": {"score": 92.0, "count": 10, "penalized": 0,
                                   "last_seen": "2026-06-30"}},
            "processed_dates": ["2026-06-30"],
        }
        arts = [{"title": "깨끗", "summary": "", "source": "한국경제"}]  # 그날 평균 100
        store = objectivity.update_media_scores(store, arts, "2026-07-01")
        # 0.9*92 + 0.1*100 = 92.8
        self.assertAlmostEqual(store["media"]["한국경제"]["score"], 92.8)
        self.assertEqual(store["media"]["한국경제"]["count"], 11)

    def test_idempotent_same_date_skipped(self):
        arts = [{"title": "깨끗", "summary": "", "source": "한국경제"}]
        store = objectivity.update_media_scores(self._empty_store(), arts, "2026-07-01")
        before = objectivity_snapshot(store)
        store = objectivity.update_media_scores(store, arts, "2026-07-01")
        self.assertEqual(objectivity_snapshot(store), before)


def objectivity_snapshot(store):
    import json
    return json.dumps(store, sort_keys=True, ensure_ascii=False)


import json  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402


class StoreIOTest(unittest.TestCase):
    def test_load_missing_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(objectivity, "MEDIA_FILE", Path(tmp) / "media.json"):
                store = objectivity.load_store()
        self.assertEqual(store, {"media": {}, "processed_dates": []})

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            mf = Path(tmp) / "media.json"
            with patch.object(objectivity, "MEDIA_FILE", mf), \
                 patch.object(objectivity, "SCORES_DIR", Path(tmp)):
                objectivity.save_store({"media": {"A": {"score": 90.0, "count": 1,
                                       "penalized": 0, "last_seen": "2026-07-01"}},
                                       "processed_dates": ["2026-07-01"]})
                store = objectivity.load_store()
        self.assertEqual(store["media"]["A"]["score"], 90.0)
        self.assertIn("updated_at", store)

    def test_article_report_saves_only_penalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(objectivity, "SCORES_DIR", Path(tmp)):
                objectivity.save_article_report("2026-07-01", [
                    {"source": "A", "category": "경제", "title": "논란이 커지고 있다",
                     "link": "L1", "score": 90, "hits": ["논란이 커지고 있다"]},
                ])
                data = json.loads((Path(tmp) / "articles-2026-07-01.json").read_text())
        self.assertEqual(data["penalized_count"], 1)
        self.assertEqual(data["articles"][0]["source"], "A")


if __name__ == "__main__":
    unittest.main()
