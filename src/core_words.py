"""코어단어: 그날 제목에서 화제어를 뽑아 클러스터링 보강·정렬 tiebreak·주제 관찰에 쓴다.

형태소 분석 없이 정규식 토큰 빈도로 근사(빈출 = 그날 화제). LLM 미사용.
- extract_core_words: 2개 이상 제목에 등장한 토큰(불용어 제외).
- core_word_stats: 코어단어별 등장 매체 수·총 기사 수·점수(매체수 + 기사수*0.2).
- top_topics: 점수 상위 n개 = 오늘의 주제.
- 가중치 저장/갱신은 Phase 2.2에서 추가.

설계: docs/superpowers/specs/2026-07-13-선별재설계-design.md §흐름 2.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCORES_DIR = ROOT / "scores"
WEIGHTS_FILE = SCORES_DIR / "core-word-weights.json"
RANK_POINTS = [5, 3, 1]   # 오늘의 주제 1·2·3위 점수
ALPHA = 0.1               # 감쇠 상수(큰 폭 변화 방지). weight += 점수*ALPHA

_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")
# 화제어가 아닌 상투 토큰(제목 표준어구). extract._TITLE_STOPWORDS 시드 + 확장.
STOPWORDS = {"오늘", "관련", "기자", "뉴스", "속보", "단독", "종합", "확대", "위해",
             "대한", "이번", "그대로", "때문", "공개", "출시", "진행"}


def extract_core_words(titles, min_freq: int = 2) -> set[str]:
    """제목들에서 min_freq개 이상 제목에 등장한 토큰(불용어 제외)을 코어단어로 뽑는다.
    빈도는 제목 단위(한 제목에서 반복돼도 1회)."""
    freq: Counter[str] = Counter()
    for title in titles:
        toks = {t for t in _TOKEN.findall(title) if t not in STOPWORDS}
        freq.update(toks)
    return {w for w, c in freq.items() if c >= min_freq}


def core_word_stats(articles, core_words) -> dict:
    """코어단어별 통계. 점수 = 등장 매체 수 + (총 기사 수 * 0.2).
    매체 다양성을 물량보다 주가중(다양성이 더 객관적)."""
    stats: dict[str, dict] = {}
    for w in core_words:
        arts = [a for a in articles if w in a.get("title", "")]
        media = {a.get("source", "") for a in arts}
        stats[w] = {"media_count": len(media), "article_count": len(arts),
                    "score": len(media) + len(arts) * 0.2}
    return stats


def top_topics(stats: dict, n: int = 3):
    """점수 상위 n개 (word, stat) 리스트. 동점은 단어명 오름차순으로 결정적."""
    return sorted(stats.items(), key=lambda kv: (-kv[1]["score"], kv[0]))[:n]


def load_weights(path: Path = WEIGHTS_FILE) -> dict:
    """코어단어 가중치 저장소. 빈 상태로 시작(수동 시드 없음, 첫날 top-3가 초기값)."""
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"weights": {}, "processed_dates": []}


def save_weights(store: dict, path: Path = WEIGHTS_FILE) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def update_core_weights(store: dict, top3, date: str, alpha: float = ALPHA) -> dict:
    """오늘의 주제 top3에 순위점수(5/3/1)를 alpha 감쇠로 누적(증분만 저장). 날짜 멱등.
    weights[word]는 증분 합이고, 정렬용 실가중치는 weight_of가 1(기본)을 더해 돌려준다."""
    if date in store.get("processed_dates", []):
        return store
    weights = store.setdefault("weights", {})
    for (word, _stat), pts in zip(top3, RANK_POINTS):
        weights[word] = weights.get(word, 0) + pts * alpha
    store.setdefault("processed_dates", []).append(date)
    return store


def weight_of(store: dict, word: str) -> float:
    """정렬 tiebreak용 코어단어 가중치 = 1(기본) + 누적 증분. 미등록 단어는 1."""
    return 1 + store.get("weights", {}).get(word, 0)


def record_topics(date: str, top3, scores_dir: Path = SCORES_DIR) -> None:
    """오늘의 주제 top3를 topics-<date>.json에 기록(observe, 활용은 나중)."""
    scores_dir = Path(scores_dir)
    scores_dir.mkdir(parents=True, exist_ok=True)
    payload = {"date": date, "topics": [
        {"word": w, "score": s.get("score", 0),
         "media_count": s.get("media_count", 0),
         "article_count": s.get("article_count", 0)} for w, s in top3]}
    (scores_dir / f"topics-{date}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
