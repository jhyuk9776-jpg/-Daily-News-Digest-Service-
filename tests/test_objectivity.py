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
        # medium 등급 = -8 (penalties.yaml 기준)
        art = {"title": "논란이 커지고 있다는 지적", "summary": ""}
        r = objectivity.objectivity_score(art)
        self.assertEqual(r["score"], 92)
        self.assertIn("논란이 커지고 있다", r["hits"])

    def test_multiple_hits_stack(self):
        # medium + medium = -16
        art = {"title": "충격을 주고 있다", "summary": "큰 파장이 예상된다"}
        r = objectivity.objectivity_score(art)
        self.assertEqual(r["score"], 84)
        self.assertEqual(len(r["hits"]), 2)

    def test_pattern_match(self):
        art = {"title": "정부가 다 했네", "summary": ""}
        r = objectivity.objectivity_score(art)
        self.assertLess(r["score"], 100)
        self.assertTrue(r["hits"])

    def test_floor_clamp(self):
        # 가속·cap 도달: 반복 감점은 per-기사 cap(45)에서 멈춘다 → score 55
        text = "논란이 커지고 있다 " * 20
        art = {"title": text, "summary": ""}
        r = objectivity.objectivity_score(art)
        self.assertEqual(r["score"], 55)


class MediaAggregateTest(unittest.TestCase):
    def _empty_store(self):
        return {"media": {}, "processed_dates": []}

    def test_new_media_uses_day_average_as_initial(self):
        arts = [
            {"title": "깨끗한 기사", "summary": "", "source": "한국경제"},
            {"title": "논란이 커지고 있다", "summary": "", "source": "한국경제"},
        ]  # 점수 100, 92 → 그날 평균 96 (medium -8)
        store = objectivity.update_media_scores(self._empty_store(), arts, "2026-07-01")
        m = store["media"]["한국경제"]
        self.assertAlmostEqual(m["score"], 96.0)
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


class ScoringConfigTest(unittest.TestCase):
    def test_load_scoring_from_real_file(self):
        cfg = objectivity.load_scoring(objectivity.PENALTIES_FILE)
        self.assertEqual(cfg["tiers"]["strong"], 15)
        self.assertEqual(cfg["escalation"]["T"], 3)
        self.assertEqual(cfg["escalation"]["cap"], 45)
        self.assertEqual(cfg["body_factor"], 0.5)
        self.assertIn("에 따르면", cfg["attribution_markers"])


class PenaltyLoaderTest(unittest.TestCase):
    def _write(self, tmp, text):
        p = Path(tmp) / "penalties.yaml"
        p.write_text(text, encoding="utf-8")
        return p

    def test_load_parses_active_observe_exclusions(self):
        text = (
            "penalties:\n"
            "  - {expr: '[가-힣]+가 다 했네', type: regex, tier: strong, weight: 15, 근거: 조롱}\n"
            "  - {expr: '아우성', type: phrase, tier: medium, weight: 8, 근거: 감정}\n"
            "observe_candidates:\n"
            "  - {expr: 이러다, type: phrase, tier: weak, weight: 3, 근거: 리드}\n"
            "exclusions:\n"
            "  - {term: 충격, reason: 사실문맥}\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            active, observe, exclusions = objectivity.load_penalties(self._write(tmp, text))
        self.assertEqual(len(active), 2)
        self.assertEqual(active[0]["weight"], 15)
        self.assertEqual(len(observe), 1)
        self.assertEqual(observe[0]["expr"], "이러다")
        self.assertEqual(exclusions[0]["term"], "충격")

    def test_load_missing_file_returns_seed(self):
        active, observe, exclusions = objectivity.load_penalties(Path("/no/such/penalties.yaml"))
        self.assertTrue(active)          # 시드 폴백은 비어있지 않다
        self.assertEqual(observe, [])
        self.assertEqual(exclusions, [])

    def test_load_skips_invalid_regex(self):
        text = (
            "penalties:\n"
            "  - {expr: '[bad', type: regex, tier: strong, weight: 15, 근거: x}\n"
            "  - {expr: 좋음, type: phrase, tier: weak, weight: 3, 근거: y}\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            active, _, _ = objectivity.load_penalties(self._write(tmp, text))
        exprs = [a["expr"] for a in active]
        self.assertIn("좋음", exprs)
        self.assertNotIn("[bad", exprs)


class GradedScoreTest(unittest.TestCase):
    P = [
        {"expr": "논란이 커지고 있다", "type": "phrase", "tier": "medium", "weight": 8, "근거": "평가"},
        {"expr": "[가-힣]+가 다 했네", "type": "regex", "tier": "strong", "weight": 15, "근거": "조롱"},
    ]
    OBS = [{"expr": "극적", "type": "phrase", "tier": "weak", "weight": 3, "근거": "묘사"}]

    def test_weights_sum_by_tier(self):
        art = {"title": "논란이 커지고 있다 반도체가 다 했네", "summary": ""}
        r = objectivity.objectivity_score(art, self.P, self.OBS)
        self.assertEqual(r["score"], 100 - 8 - 15)  # 77
        self.assertEqual(len(r["hits"]), 2)

    def test_repeat_counts_each_occurrence(self):
        art = {"title": "논란이 커지고 있다 논란이 커지고 있다", "summary": ""}
        r = objectivity.objectivity_score(art, self.P, self.OBS)
        self.assertEqual(r["score"], 100 - 16)

    def test_observe_recorded_not_deducted(self):
        art = {"title": "3살 아이 극적 구조", "summary": ""}
        r = objectivity.objectivity_score(art, self.P, self.OBS)
        self.assertEqual(r["score"], 100)          # observe는 감점하지 않음
        self.assertEqual(r["hits"], [])
        self.assertIn("극적", r["observe_hits"])

    def test_floor_clamp_with_weights(self):
        art = {"title": "반도체가 다 했네 " * 10, "summary": ""}  # cap 45에서 멈춤
        r = objectivity.objectivity_score(art, self.P, self.OBS)
        self.assertEqual(r["score"], 55)


class ChannelScoreTest(unittest.TestCase):
    P = [
        {"expr": "아우성", "type": "phrase", "tier": "medium", "weight": 8,
         "scope": "text", "근거": "감정"},
        {"expr": "\\?$", "type": "regex", "tier": "medium", "weight": 8,
         "scope": "title", "근거": "물음표"},
    ]
    SCORING = {"tiers": {}, "escalation": {"T": 3, "step": 5, "cap": 45},
               "body_factor": 0.5, "attribution_markers": []}

    def test_title_scope_only_matches_title(self):
        # 물음표는 제목에만 감점(scope:title). 리드의 물음표는 무시.
        r = objectivity.score_article(
            {"title": "정말일까?", "lead": "", "body": ""}, self.P, [], self.SCORING)
        self.assertEqual(r["points"], 8)
        r2 = objectivity.score_article(
            {"title": "무역흑자 361억달러", "lead": "정말일까?", "body": ""},
            self.P, [], self.SCORING)
        self.assertEqual(r2["points"], 0)

    def test_body_factor_halves_body_hit(self):
        # 본문의 '아우성'(scope:text는 title+lead만; body는 별도) → body_factor 검증용 body scope
        P = [{"expr": "아우성", "type": "phrase", "tier": "medium", "weight": 8,
              "scope": "body", "근거": "감정"}]
        r = objectivity.score_article(
            {"title": "", "lead": "", "body": "여기저기 아우성"}, P, [], self.SCORING)
        self.assertEqual(r["points"], 4.0)   # 8 × body_factor 0.5

    def test_escalation_above_threshold(self):
        # 5회 등장: raw=40, n_hits=5>T3 → +step*(5-3)=10 → 50, cap45 → 45
        art = {"title": "아우성 아우성 아우성 아우성 아우성", "lead": "", "body": ""}
        r = objectivity.score_article(art, self.P, [], self.SCORING)
        self.assertEqual(r["n_hits"], 5)
        self.assertEqual(r["points"], 45)    # cap
        self.assertEqual(r["score"], 55)

    def test_below_threshold_is_linear(self):
        art = {"title": "아우성 아우성", "lead": "", "body": ""}
        r = objectivity.score_article(art, self.P, [], self.SCORING)
        self.assertEqual(r["points"], 16)    # 2×8, 가속 없음(n=2≤3)


class PenaltyMemoTest(unittest.TestCase):
    P = [{"expr": "아우성", "type": "phrase", "tier": "medium", "weight": 8, "근거": "감정 과장"}]

    def test_aggregates_by_expr_and_source(self):
        records = [
            {"source": "매일신문", "hits": ["아우성"]},
            {"source": "매일신문", "hits": ["아우성"]},
            {"source": "한국경제", "hits": []},
        ]
        memo = objectivity.penalty_memo(records, self.P)
        self.assertEqual(memo["total_deducted"], 16)
        self.assertEqual(memo["by_expr"]["아우성"]["count"], 2)
        self.assertEqual(memo["by_expr"]["아우성"]["근거"], "감정 과장")
        self.assertEqual(memo["by_source"]["매일신문"], 16)

    def test_empty_when_no_hits(self):
        memo = objectivity.penalty_memo([{"source": "A", "hits": []}], self.P)
        self.assertEqual(memo["total_deducted"], 0)
        self.assertEqual(memo["by_expr"], {})


class ObservationAxisTest(unittest.TestCase):
    def test_attribution_count(self):
        ch = {"title": "정부에 따르면 흑자", "lead": "관계자는 사실이라고 밝혔다", "body": ""}
        n = objectivity.attribution_count(
            ch, ["에 따르면", "라고 밝혔다", "고 밝혔다"])
        self.assertEqual(n, 2)   # '에 따르면' 1 + '고 밝혔다' 1

    def test_outlier_only_singleton_with_hit(self):
        arts = [
            # 단독 + 감점(아우성) → 이상치
            {"title": "혼자만 아우성", "summary": "", "link": "L1", "source": "A"},
            # 교차(같은 제목 다른 매체) + 감점 → 이상치 아님(단독 아님)
            {"title": "공동 논란이 커지고 있다", "summary": "", "link": "L2", "source": "B"},
            {"title": "공동 논란이 커지고 있다", "summary": "", "link": "L3", "source": "C"},
            # 단독 + 무감점 → 이상치 아님
            {"title": "혼자 깨끗한 기사", "summary": "", "link": "L4", "source": "D"},
        ]
        flags = objectivity.outlier_flags(arts)
        self.assertTrue(flags["L1"])
        self.assertFalse(flags["L2"])
        self.assertFalse(flags["L4"])


if __name__ == "__main__":
    unittest.main()
