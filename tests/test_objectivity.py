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
                objectivity.save_store({"media": {"A": {"penalty_points_total": 8.0,
                                       "article_count": 2, "attribution_total": 0,
                                       "outlier_total": 0, "density_per_1000": 4000.0,
                                       "count": 2, "last_seen": "2026-07-01"}},
                                       "processed_dates": ["2026-07-01"]})
                store = objectivity.load_store()
        self.assertEqual(store["media"]["A"]["density_per_1000"], 4000.0)
        self.assertIn("updated_at", store)


class RankHistoryTest(unittest.TestCase):
    def _store(self):
        return {"media": {
            "고선택": {"selection_rate": 0.75, "win_total": 6, "appear_total": 8, "article_count": 8},
            "저선택": {"selection_rate": 0.25, "win_total": 2, "appear_total": 8, "article_count": 8},
            "중선택": {"selection_rate": 0.50, "win_total": 4, "appear_total": 8, "article_count": 8},
            "등장없음": {"selection_rate": None, "win_total": 0, "appear_total": 0, "article_count": 0},
        }}

    def test_rank_history_uses_selection_rate(self):
        ranks = objectivity.compute_selection_ranks(self._store())
        self.assertEqual(ranks["고선택"], 1)  # 선택률 높을수록 → 1위
        self.assertEqual(ranks["중선택"], 2)
        self.assertEqual(ranks["저선택"], 3)

    def test_ranks_exclude_zero_appear(self):
        ranks = objectivity.compute_selection_ranks(self._store())
        self.assertNotIn("등장없음", ranks)

    def test_compute_ranks_removed(self):
        self.assertFalse(hasattr(objectivity, "compute_ranks"))

    def test_update_media_scores_removed(self):
        self.assertFalse(hasattr(objectivity, "update_media_scores"))

    def test_selection_ranks_filter_on_appear(self):
        # density 필드(article_count) 없이 선택률 데이터만 있어도 순위가 잡혀야 한다.
        store = {"media": {"A": {"appear_total": 2, "win_total": 2, "selection_rate": 1.0}}}
        self.assertEqual(objectivity.compute_selection_ranks(store), {"A": 1})

    def test_history_appends_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(objectivity, "SCORES_DIR", Path(tmp)), \
                 patch.object(objectivity, "RANK_HISTORY_FILE", Path(tmp) / "media-rank-history.json"):
                objectivity.update_rank_history("2026-07-09", {"저밀도": 1, "고밀도": 2})
                objectivity.update_rank_history("2026-07-10", {"고밀도": 1, "저밀도": 2})
                # 같은 날짜 재실행 → 덮어씀(중복 없음)
                objectivity.update_rank_history("2026-07-10", {"저밀도": 1, "고밀도": 2})
                hist = objectivity.load_rank_history()
        dates = [e["date"] for e in hist["history"]]
        self.assertEqual(dates, ["2026-07-09", "2026-07-10"])  # 날짜순, 중복 없음
        self.assertEqual(hist["history"][-1]["ranks"], {"저밀도": 1, "고밀도": 2})


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


if __name__ == "__main__":
    unittest.main()
