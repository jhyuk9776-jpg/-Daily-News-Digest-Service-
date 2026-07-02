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

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from curate import (  # 날짜창·출처목록 재사용(격리: 단방향 의존)
    SOURCES_FILE,
    in_date_window,
    load_priority_map,
)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw"
SCORES_DIR = ROOT / "scores"
MEDIA_FILE = SCORES_DIR / "media.json"
KST = timezone(timedelta(hours=9))

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


def update_media_scores(store: dict, dated_articles: list[dict], date: str) -> dict:
    """그날 기사들을 매체별로 채점해 EWMA로 store에 누적한다(멱등)."""
    if date in store.get("processed_dates", []):
        return store  # 이미 처리한 날짜 — 이중 반영 방지

    # 매체별 그날 점수 모으기
    by_source: dict[str, list[int]] = {}
    penalized: dict[str, int] = {}
    for art in dated_articles:
        source = art.get("source", "")
        r = objectivity_score(art)
        by_source.setdefault(source, []).append(r["score"])
        if r["hits"]:
            penalized[source] = penalized.get(source, 0) + 1

    media = store.setdefault("media", {})
    for source, scores in by_source.items():
        day_avg = sum(scores) / len(scores)
        if source in media:
            prev = media[source]
            prev["score"] = (1 - EWMA_ALPHA) * prev["score"] + EWMA_ALPHA * day_avg
            prev["count"] += len(scores)
            prev["penalized"] += penalized.get(source, 0)
            prev["last_seen"] = date
        else:
            media[source] = {
                "score": day_avg,
                "count": len(scores),
                "penalized": penalized.get(source, 0),
                "last_seen": date,
            }

    store.setdefault("processed_dates", []).append(date)
    return store


def load_store() -> dict:
    if MEDIA_FILE.exists():
        with MEDIA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"media": {}, "processed_dates": []}


def save_store(store: dict) -> None:
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    store["updated_at"] = datetime.now(KST).isoformat(timespec="seconds")
    with MEDIA_FILE.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def save_article_report(date: str, records: list[dict]) -> None:
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    penalized = [r for r in records if r["score"] < BASELINE]
    payload = {
        "date": date,
        "scored": len(records),
        "penalized_count": len(penalized),
        "articles": penalized,
    }
    with (SCORES_DIR / f"articles-{date}.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def active_sources() -> set[str]:
    """sources.yaml에 등록된 현재 활성 매체명 집합.

    제외된(더 이상 sources.yaml에 없는) 매체는 채점 대상에서 뺀다. 과거 raw를
    백필해도 옛 출처가 다시 점수에 잡히지 않게 하는 방어선.
    """
    return {source for (_cat, source) in load_priority_map(SOURCES_FILE)}


def dated_articles_for(date: str) -> list[dict]:
    path = RAW_DIR / f"{date}.json"
    if not path.exists():
        raise FileNotFoundError(f"수집 결과가 없음: {path} (먼저 fetch.py 실행)")
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    # 날짜창 기준은 now()가 아니라 그 raw 파일의 날짜(정오 KST). 재백필 시 과거 파일도 정확.
    ref = datetime.fromisoformat(date).replace(tzinfo=KST) + timedelta(hours=12)
    active = active_sources()
    return [a for a in raw["articles"]
            if in_date_window(a, ref) and a.get("source", "") in active]


def process_date(store: dict, date: str) -> dict:
    """하루치 raw를 채점해 store에 누적하고 감점 리포트를 저장한다."""
    articles = dated_articles_for(date)
    already = date in store.get("processed_dates", [])
    store = update_media_scores(store, articles, date)
    if not already:
        records = []
        for a in articles:
            r = objectivity_score(a)
            records.append({
                "source": a.get("source", ""),
                "category": a.get("category", ""),
                "title": a.get("title", ""),
                "link": a.get("link", ""),
                "score": r["score"],
                "hits": r["hits"],
            })
        save_article_report(date, records)
    return store


def run_backfill() -> dict:
    """raw/*.json을 날짜 오름차순으로 전부 재처리해 store를 새로 구축한다."""
    store = {"media": {}, "processed_dates": []}
    dates = sorted(p.stem for p in RAW_DIR.glob("*.json"))
    for date in dates:
        store = process_date(store, date)
    save_store(store)
    print(f"백필 완료: {len(dates)}일 처리, 매체 {len(store['media'])}곳")
    return store


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="매체 객관성 점수 축적기(observe-only)")
    parser.add_argument("date", nargs="?", help="처리할 날짜 YYYY-MM-DD (기본: 오늘 KST)")
    parser.add_argument("--backfill", action="store_true",
                        help="raw/*.json 전부 재처리(전체 재구축)")
    args = parser.parse_args()

    if args.backfill:
        run_backfill()
        return 0

    date = args.date or datetime.now(KST).strftime("%Y-%m-%d")
    store = load_store()
    try:
        store = process_date(store, date)
    except FileNotFoundError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    save_store(store)

    print(f"=== 객관성 점수 축적 ({date}) ===")
    for source, m in sorted(store["media"].items(), key=lambda kv: kv[1]["score"]):
        print(f"  {m['score']:5.1f} · {source} "
              f"(표본 {m['count']}, 감점 {m['penalized']})")
    print(f"저장됨: {MEDIA_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
