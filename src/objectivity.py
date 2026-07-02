"""Phase 2: 매체 객관성 점수 축적기 (observe-only, record-only).

요약하지 않은 수집 기사까지 감점 휴리스틱으로 채점해 매체별 객관성 점수를
이동평균(EWMA)으로 누적한다. 선별·랭킹에는 반영하지 않는다(관찰만).

설계: docs/superpowers/specs/2026-07-01-objectivity-scorer-design.md
감점 사전 시드: AI_CONTEXT.md §6 "피해야 할 표현".

실행:
    python3 src/objectivity.py            # 오늘(KST) 채점·누적
    python3 src/objectivity.py 2026-06-30 # 특정 날짜
    python3 src/objectivity.py --backfill # raw/*.json 전부 재구축
"""

from __future__ import annotations

import re

BASELINE = 100
PENALTY = 10
FLOOR = 0
EWMA_ALPHA = 0.1

# 감점 사전(고정밀 시드). 단일 모호어("충격" 단독 등)는 오탐 위험으로 제외.
PENALTY_PHRASES = [
    "논란이 커지고 있다",
    "충격을 주고 있다",
    "큰 파장이 예상된다",
    "업계가 주목하고 있다",
]
PENALTY_PATTERNS = [
    re.compile(r"[가-힣]+가 다 했네"),  # "~가 다 했네" 류 평가·조롱
]


def objectivity_score(article: dict) -> dict:
    """기사 1건의 객관성 점수(감점 중심)와 감점 근거를 계산한다."""
    text = f"{article.get('title', '')} {article.get('summary', '')}"
    hits: list[str] = []
    # 출현 횟수마다 감점(스펙 §4 "매칭마다"). 평가어가 반복될수록 더 깎여
    # FLOOR 클램프가 실제로 도달 가능해진다.
    for phrase in PENALTY_PHRASES:
        hits.extend([phrase] * text.count(phrase))
    for pat in PENALTY_PATTERNS:
        hits.extend(m.group(0) for m in pat.finditer(text))
    score = max(FLOOR, BASELINE - PENALTY * len(hits))
    return {"score": score, "hits": hits}
