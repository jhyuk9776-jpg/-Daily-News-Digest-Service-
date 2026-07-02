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
from datetime import datetime  # noqa: E402
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


class ProcessAndBackfillTest(unittest.TestCase):
    def _write_raw(self, raw_dir, date, articles):
        payload = {"date": date, "articles": articles}
        (raw_dir / f"{date}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _art(self, source, title, iso):
        return {"category": "경제", "source": source, "title": title,
                "summary": "", "link": f"L-{title}", "published_iso": iso}

    def test_process_date_updates_store_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            raw_dir = tmp_p / "raw"; raw_dir.mkdir()
            # 오늘 날짜를 고정하기 위해 window를 넉넉히: iso를 오늘로
            today = datetime.now(objectivity.KST).date().isoformat()
            self._write_raw(raw_dir, today, [
                self._art("한국경제", "깨끗한 기사", f"{today}T01:00:00+00:00"),
                self._art("한국경제", "논란이 커지고 있다", f"{today}T01:00:00+00:00"),
            ])
            with patch.object(objectivity, "RAW_DIR", raw_dir), \
                 patch.object(objectivity, "SCORES_DIR", tmp_p / "scores"), \
                 patch.object(objectivity, "MEDIA_FILE", tmp_p / "scores" / "media.json"):
                store = objectivity.process_date(
                    {"media": {}, "processed_dates": []}, today)
                self.assertIn("한국경제", store["media"])
                self.assertEqual(store["media"]["한국경제"]["count"], 2)
                report = json.loads(
                    (tmp_p / "scores" / f"articles-{today}.json").read_text())
                self.assertEqual(report["penalized_count"], 1)

    def test_backfill_processes_old_files(self):
        # 과거 날짜(오래된 raw)도 걸러지지 않고 처리돼야 한다(now()가 아니라 파일 날짜 기준).
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            raw_dir = tmp_p / "raw"; raw_dir.mkdir()
            old = "2020-01-15"  # 한참 과거 — now() 기준이면 전부 걸러질 날짜
            self._write_raw(raw_dir, old, [
                self._art("A", "깨끗", "2020-01-15T01:00:00+00:00")])
            with patch.object(objectivity, "RAW_DIR", raw_dir), \
                 patch.object(objectivity, "SCORES_DIR", tmp_p / "scores"), \
                 patch.object(objectivity, "MEDIA_FILE", tmp_p / "scores" / "media.json"), \
                 patch.object(objectivity, "active_sources", return_value={"A"}):
                store = objectivity.run_backfill()
        self.assertIn(old, store["processed_dates"])
        self.assertIn("A", store["media"])  # 파일 날짜 기준이라 통과
        self.assertEqual(store["media"]["A"]["count"], 1)


class ActiveSourceFilterTest(unittest.TestCase):
    def _write_raw(self, raw_dir, date, articles):
        (raw_dir / f"{date}.json").write_text(
            json.dumps({"date": date, "articles": articles}, ensure_ascii=False),
            encoding="utf-8")

    def test_dated_articles_excludes_inactive_source(self):
        # sources.yaml에 없는 매체(제외됨)는 채점 대상에서 빠진다.
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp)
            self._write_raw(raw_dir, "2020-01-15", [
                {"category": "경제", "source": "한국경제", "title": "t1",
                 "summary": "", "link": "L1", "published_iso": "2020-01-15T01:00:00+00:00"},
                {"category": "경제", "source": "이코노미스트 타임스", "title": "t2",
                 "summary": "", "link": "L2", "published_iso": "2020-01-15T01:00:00+00:00"},
            ])
            with patch.object(objectivity, "RAW_DIR", raw_dir), \
                 patch.object(objectivity, "active_sources",
                              return_value={"한국경제"}):
                arts = objectivity.dated_articles_for("2020-01-15")
        sources = {a["source"] for a in arts}
        self.assertIn("한국경제", sources)
        self.assertNotIn("이코노미스트 타임스", sources)


if __name__ == "__main__":
    unittest.main()
