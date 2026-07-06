"""Phase 2: 매체 객관성 점수 축적기 (observe-only, record-only).

요약하지 않은 수집 기사까지 감점 휴리스틱으로 채점해 매체별 객관성 점수를
이동평균(EWMA)으로 누적한다. 선별·랭킹에는 반영하지 않는다(관찰만).

설계: 기획/시스템기획/기능설계/04-객관성-점수축적기.md
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

import yaml

from curate import (  # 날짜창·출처목록 재사용(격리: 단방향 의존)
    SOURCES_FILE,
    in_date_window,
    load_priority_map,
)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw"
SCORES_DIR = ROOT / "scores"
MEDIA_FILE = SCORES_DIR / "media.json"
PENALTIES_FILE = ROOT / "penalties.yaml"
KST = timezone(timedelta(hours=9))

BASELINE = 100
FLOOR = 0
EWMA_ALPHA = 0.1

# 시드 폴백(penalties.yaml 없을 때만). AI_CONTEXT §6 "피해야 할 표현".
_SEED_PENALTIES = [
    {"expr": "논란이 커지고 있다", "type": "phrase", "tier": "medium", "weight": 10, "근거": "평가성 상투구"},
    {"expr": "충격을 주고 있다", "type": "phrase", "tier": "medium", "weight": 10, "근거": "감정 과장"},
    {"expr": "큰 파장이 예상된다", "type": "phrase", "tier": "medium", "weight": 10, "근거": "전망성 상투구"},
    {"expr": "업계가 주목하고 있다", "type": "phrase", "tier": "medium", "weight": 10, "근거": "관심 예단"},
    {"expr": "[가-힣]+가 다 했네", "type": "regex", "tier": "strong", "weight": 10, "근거": "조롱조 단정"},
]

_DEFAULT_SCORING = {
    "tiers": {"strong": 15, "medium": 8, "weak": 3},
    "escalation": {"T": 3, "step": 5, "cap": 45},
    "body_factor": 0.5,
    "attribution_markers": ["에 따르면", "라고 밝혔다", "고 밝혔다", "고 말했다",
                            "라고 말했다", "측은", "측이", "당국은"],
}


def _normalize_entry(entry: dict) -> dict | None:
    """감점 항목 검증·정규화. 정규식이 잘못되면 None(로드 시 건너뜀)."""
    expr = entry.get("expr")
    if not expr:
        return None
    etype = entry.get("type", "phrase")
    if etype == "regex":
        try:
            re.compile(expr)
        except re.error:
            print(f"경고: 잘못된 정규식 건너뜀 — {expr!r}", file=sys.stderr)
            return None
    return {
        "expr": expr,
        "type": etype,
        "tier": entry.get("tier", "medium"),
        "weight": int(entry.get("weight", 8)),
        "근거": entry.get("근거", ""),
        "scope": entry.get("scope", "text"),
    }


def load_penalties(path: Path = PENALTIES_FILE):
    """penalties.yaml을 읽어 (active, observe, exclusions)로 돌려준다.

    파일이 없으면 시드 사전으로 폴백(observe·exclusions는 빈 리스트).
    잘못된 정규식 항목은 건너뛴다(전체 로드 실패 방지).
    """
    path = Path(path)
    if not path.exists():
        return list(_SEED_PENALTIES), [], []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    active = [e for e in (_normalize_entry(x) for x in data.get("penalties", []) or []) if e]
    observe = [e for e in (_normalize_entry(x) for x in data.get("observe_candidates", []) or []) if e]
    exclusions = data.get("exclusions", []) or []
    return active, observe, exclusions


def load_scoring(path: Path = PENALTIES_FILE) -> dict:
    """penalties.yaml의 scoring 블록·attribution_markers를 읽는다(없으면 시드)."""
    path = Path(path)
    if not path.exists():
        return {k: (dict(v) if isinstance(v, dict) else (v if isinstance(v, float) else list(v)))
                for k, v in _DEFAULT_SCORING.items()}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = {k: (dict(v) if isinstance(v, dict) else (v if isinstance(v, float) else list(v)))
           for k, v in _DEFAULT_SCORING.items()}
    for key in ("tiers", "escalation"):
        cfg[key].update(data.get("scoring", {}).get(key, {}) or {})
    if "scoring" in data and "body_factor" in data["scoring"]:
        cfg["body_factor"] = float(data["scoring"]["body_factor"])
    if data.get("attribution_markers"):
        cfg["attribution_markers"] = list(data["attribution_markers"])
    return cfg


ACTIVE_PENALTIES, OBSERVE_PENALTIES, EXCLUSIONS = load_penalties()
SCORING = load_scoring()


def _count_matches(entry: dict, text: str) -> int:
    if entry["type"] == "regex":
        return len(re.findall(entry["expr"], text))
    return text.count(entry["expr"])


def _scope_text(scope: str, channels: dict) -> str:
    if scope == "text":
        return f"{channels.get('title', '')} {channels.get('lead', '')}"
    return channels.get(scope, "")


def score_article(channels: dict, penalties=None, observe=None, scoring=None) -> dict:
    """기사 1건을 채널별로 채점한다(등급·scope·가속·차등가중).

    channels: {"title","lead","body"} 중 있는 것만. 없는 키는 빈 문자열.
    body 채널 매칭은 scoring.body_factor로 가중. 가속은 n_hits가 T 초과 시 볼록 가산.
    """
    penalties = ACTIVE_PENALTIES if penalties is None else penalties
    observe = OBSERVE_PENALTIES if observe is None else observe
    scoring = SCORING if scoring is None else scoring
    esc = scoring["escalation"]
    body_factor = scoring["body_factor"]

    hits: list[str] = []
    raw = 0.0
    n_hits = 0
    for p in penalties:
        scope = p.get("scope", "text")
        c = _count_matches(p, _scope_text(scope, channels))
        if c:
            factor = body_factor if scope == "body" else 1.0
            raw += p["weight"] * c * factor
            n_hits += c
            hits.extend([p["expr"]] * c)

    observe_hits: list[str] = []
    for p in observe:
        scope = p.get("scope", "text")
        c = _count_matches(p, _scope_text(scope, channels))
        if c:
            observe_hits.extend([p["expr"]] * c)

    points = raw + esc["step"] * max(0, n_hits - esc["T"])
    points = min(esc["cap"], points)
    score = max(FLOOR, BASELINE - points)
    return {"points": points, "hits": hits, "n_hits": n_hits,
            "observe_hits": observe_hits, "score": int(score)}


def objectivity_score(article: dict, penalties=None, observe=None) -> dict:
    """호환 래퍼: 기사(title+summary)를 title/lead 채널로 채점."""
    channels = {"title": article.get("title", ""),
                "lead": article.get("summary", ""), "body": ""}
    return score_article(channels, penalties, observe)


def penalty_memo(records: list[dict], penalties=None) -> dict:
    """그날 기사 기록의 hits를 집계해 "무엇이·왜·얼마나" 감점됐는지 요약한다.

    입력: records = [{"source":..., "hits":[expr,...]}...]
    출력: {total_deducted, by_expr:{expr:{count,deducted,근거}}, by_source:{src:deducted}}
    """
    penalties = ACTIVE_PENALTIES if penalties is None else penalties
    weight = {p["expr"]: p["weight"] for p in penalties}
    reason = {p["expr"]: p.get("근거", "") for p in penalties}
    by_expr: dict[str, dict] = {}
    by_source: dict[str, int] = {}
    total = 0
    for rec in records:
        for expr in rec.get("hits", []):
            w = weight.get(expr, 0)
            total += w
            e = by_expr.setdefault(expr, {"count": 0, "deducted": 0, "근거": reason.get(expr, "")})
            e["count"] += 1
            e["deducted"] += w
            src = rec.get("source", "")
            by_source[src] = by_source.get(src, 0) + w
    return {"total_deducted": total, "by_expr": by_expr, "by_source": by_source}


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
        "penalty_memo": penalty_memo(records),
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
