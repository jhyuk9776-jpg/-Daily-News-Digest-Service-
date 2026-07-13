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


if __name__ == "__main__":
    unittest.main()
