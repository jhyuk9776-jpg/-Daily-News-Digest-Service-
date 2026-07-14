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


# 라벨 예시의 실제 제목(홍보성 평가어는 헤드라인에 산다 → 객관성은 제목+본문을 함께 본다).
PROMO_TITLE = "지속가능한 미래 그리는 JB금융, 작년 ESG 성과 입증"
GOOD_TITLE = '"스타벅스 가야지"…고교야구 대회 중 \'광주 조롱 논란\' 불거져'


class LabelObjectivityTest(unittest.TestCase):
    def test_promo_article_penalized(self):
        # 감점 1호(JB금융 ESG): 헤드라인 "성과 입증" 홍보성 평가어 → 기존 룰이 감점
        body = (FIX / "label_zdnet_esg.txt").read_text(encoding="utf-8")
        r = objectivity.body_objectivity(body, PROMO_TITLE)
        self.assertGreater(r["points"], 0)
        self.assertTrue(any("입증" in h for h in r["hits"]))

    def test_good_example_low_penalty(self):
        # 예시 1호(배재고 스타벅스): 객관적 사건 보도 → 홍보성 감점 미발화
        body = (FIX / "label_naver_088.txt").read_text(encoding="utf-8")
        r = objectivity.body_objectivity(body, GOOD_TITLE)
        self.assertFalse(any("입증" in h for h in r["hits"]))


class BodyRichnessTest(unittest.TestCase):
    def test_rich_body_has_positive_density(self):
        # 감점 1호는 홍보성이지만 증거는 풍부(수치·%·전년대비·기관) → 밀도 > 0
        body = (FIX / "label_zdnet_esg.txt").read_text(encoding="utf-8")
        self.assertGreater(objectivity.body_richness(body), 0.0)

    def test_empty_body_zero(self):
        self.assertEqual(objectivity.body_richness(""), 0.0)

    def test_evidence_signals_counts_all_five(self):
        import curate
        text = "통계청은 전년 대비 3.5% 늘었다고 \"밝혔다\""
        self.assertEqual(curate.evidence_signals(text), 5)  # 숫자·%·기관·인용·기간


class SourceCoverageTest(unittest.TestCase):
    def test_institution_sentence_counts(self):
        # 독립기관(통계청) 인용 문장 → 근거 인정
        self.assertAlmostEqual(objectivity.source_coverage("통계청은 3.5% 올랐다고 밝혔다."), 1.0)

    def test_independent_attribution_counts(self):
        # 귀속표지 있고 자기지칭어 없음 → 인정
        self.assertAlmostEqual(objectivity.source_coverage("연구진은 결과를 발표했다."), 1.0)

    def test_self_reference_excluded(self):
        # 자기 보고서 인용은 독립 출처 아님 → 제외
        self.assertEqual(objectivity.source_coverage("회사 보고서에 따르면 성장했다고 밝혔다."), 0.0)

    def test_bare_number_not_sourced(self):
        # 출처 없는 단순 수치는 근거로 안 침
        self.assertEqual(objectivity.source_coverage("매출이 100억이다."), 0.0)

    def test_empty_zero(self):
        self.assertEqual(objectivity.source_coverage(""), 0.0)

    def test_promo_label_zero(self):
        # 감점1호(JB금융): 전부 자기인용 → 근거성 0
        body = (FIX / "label_zdnet_esg.txt").read_text(encoding="utf-8")
        self.assertEqual(objectivity.source_coverage(body), 0.0)

    def test_good_label_positive(self):
        # 예시1호(배재고): 독립 인용 존재 → 0보다 큼
        body = (FIX / "label_naver_088.txt").read_text(encoding="utf-8")
        self.assertGreater(objectivity.source_coverage(body), 0.2)


class RepresentativeScoreTest(unittest.TestCase):
    def test_good_beats_promo(self):
        good_body = (FIX / "label_naver_088.txt").read_text(encoding="utf-8")
        promo_body = (FIX / "label_zdnet_esg.txt").read_text(encoding="utf-8")
        g = objectivity.representative_score(GOOD_TITLE, good_body)
        p = objectivity.representative_score(PROMO_TITLE, promo_body)
        # 홍보(감점8)는 객관성 칼럼에서 손해 → 총합에서 객관 기사에 진다
        self.assertGreater(g["total"], p["total"])
        self.assertAlmostEqual(g["objectivity"], 1.0)   # 감점 0
        self.assertLess(p["objectivity"], 1.0)          # 감점 8

    def test_total_formula(self):
        r = objectivity.representative_score("", '숫자 3개와 통계청 인용 "있다".')
        self.assertAlmostEqual(r["total"], 0.6 * r["objectivity"] + 0.4 * r["coverage"], places=6)


if __name__ == "__main__":
    unittest.main()
