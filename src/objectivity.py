"""Phase 2: 매체 객관성 점수 축적기 (observe-only, record-only).

요약하지 않은 수집 기사까지 감점 휴리스틱으로 채점해 매체별 감점 밀도
(1000건당 감점 point, 낮을수록 객관적)를 누적한다. 선별·랭킹에는 반영하지 않는다(관찰만).

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

from curate import (  # 날짜창·출처목록·정규화·증거신호 재사용(격리: 단방향 의존)
    SOURCES_FILE,
    evidence_signals,
    in_date_window,
    load_priority_map,
    normalize_title,
)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw"
SCORES_DIR = ROOT / "scores"
MEDIA_FILE = SCORES_DIR / "media.json"
RANK_HISTORY_FILE = SCORES_DIR / "media-rank-history.json"
PENALTIES_FILE = ROOT / "penalties.yaml"
KST = timezone(timedelta(hours=9))

BASELINE = 100
FLOOR = 0

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
    scope=="text" 항목은 제목+리드(전체 가중) 외에 body도 body_factor 가중으로 추가 검사한다
    (트랙1 래퍼는 body=""를 전달하므로 동작 불변).
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
        # text scope 항목: body도 body_factor 가중으로 추가 검사
        if scope == "text":
            body_text = channels.get("body", "")
            cb = _count_matches(p, body_text) if body_text else 0
            if cb:
                raw += p["weight"] * cb * body_factor
                n_hits += cb
                hits.extend([p["expr"]] * cb)

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


def attribution_count(channels: dict, markers=None) -> int:
    """제목+리드에서 귀속(출처 명시) 표지 등장수(② 중립 관찰축, 감점 아님).

    긴 표지가 짧은 표지를 포함할 때 이중 계산을 막기 위해 정규식 교대(alternation)로
    비겹침 최장 일치를 사용한다(예: '라고 밝혔다' 매칭 후 '고 밝혔다' 재계산 방지).
    """
    markers = SCORING["attribution_markers"] if markers is None else markers
    if not markers:
        return 0
    text = f"{channels.get('title','')} {channels.get('lead','')}"
    # 긴 표지가 먼저 소비되도록 길이 내림차순 정렬
    pattern = "|".join(re.escape(m) for m in sorted(markers, key=len, reverse=True))
    return len(re.findall(pattern, text))


def outlier_flags(articles: list[dict]) -> dict:
    """④ 교차 이상치: 단독(제목그룹 distinct source==1) & 감점 hit 동반 기사 표시."""
    groups: dict[str, set] = {}
    for a in articles:
        groups.setdefault(normalize_title(a.get("title", "")), set()).add(a.get("source", ""))
    flags: dict[str, bool] = {}
    for a in articles:
        link = a.get("link", "")
        if not link:
            continue
        norm = normalize_title(a.get("title", ""))
        singleton = len(groups[norm]) == 1
        has_hit = bool(score_article(
            {"title": a.get("title", ""), "lead": a.get("summary", ""), "body": ""})["hits"])
        flags[link] = singleton and has_hit
    return flags


def objectivity_score(article: dict, penalties=None, observe=None) -> dict:
    """호환 래퍼: 기사(title+summary)를 title/lead 채널로 채점."""
    channels = {"title": article.get("title", ""),
                "lead": article.get("summary", ""), "body": ""}
    return score_article(channels, penalties, observe)


def body_objectivity(body: str, title: str = "", penalties=None, observe=None) -> dict:
    """기사 객관성(감점) 채점. 제목+본문 전체를 본다(제목만 채점하던 걸 본문까지 확장).
    title="" 이면 제목 전용 룰(scope:title)은 미발화하고 본문만 채점한다.
    scope=='text' 룰은 제목+리드(전체 가중) + body(body_factor 0.5 가중)에 적용된다."""
    channels = {"title": title, "lead": "", "body": body}
    return score_article(channels, penalties, observe)


def body_richness(body: str) -> float:
    """본문의 증거 신호 밀도(1000자당). 본문은 길어 절대개수 대신 밀도로 정규화한다."""
    if not body:
        return 0.0
    return evidence_signals(body) / max(len(body), 1) * 1000


# 문장 끝: 종결부호 뒤에 공백/문자열끝, 또는 개행. 소수점(3.5)은 뒤에 숫자가 와서 안 쪼갬.
_SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")


def sentence_coverage(body: str) -> float:
    """본문 문장 중 증거 신호(숫자·%·기관·인용·기간)를 담은 문장 비율(0~1).
    길이가 아니라 문장 단위로 정규화 → 긴 기사에 불리하지 않고 상한 1.0."""
    sents = [s for s in _SENT_SPLIT.split(body) if s.strip()]
    if not sents:
        return 0.0
    return sum(1 for s in sents if evidence_signals(s) > 0) / len(sents)


def penalty_memo(records: list[dict], penalties=None) -> dict:
    """그날 기사 기록의 hits를 집계해 "무엇이·왜·얼마나" 감점됐는지 요약한다.

    입력: records = [{"source":..., "hits":[expr,...]}...]
    출력: {total_deducted, by_expr:{expr:{count,deducted,근거}}, by_source:{src:deducted}}
    주의: 여기 합계는 표현별 raw weight 합(가속·cap·body_factor 적용 전)이라
    리포트의 total_points(실제 부과 point)와 가속 발화 시 어긋날 수 있다.
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
    """그날 기사들을 매체별로 채점해 감점 밀도로 누적한다(멱등)."""
    if date in store.get("processed_dates", []):
        return store

    flags = outlier_flags(dated_articles)
    agg: dict[str, dict] = {}
    for art in dated_articles:
        source = art.get("source", "")
        ch = {"title": art.get("title", ""), "lead": art.get("summary", ""), "body": ""}
        r = score_article(ch)
        a = agg.setdefault(source, {"points": 0.0, "count": 0, "attr": 0, "outlier": 0})
        a["points"] += r["points"]
        a["count"] += 1
        a["attr"] += attribution_count(ch)
        a["outlier"] += 1 if flags.get(art.get("link", "")) else 0

    media = store.setdefault("media", {})
    for source, a in agg.items():
        m = media.setdefault(source, {"penalty_points_total": 0.0, "article_count": 0,
                                      "attribution_total": 0, "outlier_total": 0,
                                      "density_per_1000": 0.0, "count": 0, "last_seen": date})
        m["penalty_points_total"] += a["points"]
        m["article_count"] += a["count"]
        m["attribution_total"] += a["attr"]
        m["outlier_total"] += a["outlier"]
        m["count"] = m["article_count"]
        m["last_seen"] = date
        m["density_per_1000"] = (m["penalty_points_total"] / m["article_count"] * 1000
                                 if m["article_count"] else 0.0)

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


def compute_ranks(store: dict) -> dict:
    """표본이 있는 매체를 감점 밀도 오름차순(낮을수록 객관적)으로 1위부터 매긴다.
    동밀도는 매체명으로 안정 정렬해 결정적이다."""
    media = store.get("media", {})
    ranked = sorted(
        (s for s, m in media.items() if m.get("article_count", m.get("count", 0)) > 0),
        key=lambda s: (media[s].get("density_per_1000", 0.0), s),
    )
    return {s: i + 1 for i, s in enumerate(ranked)}


def load_rank_history() -> dict:
    if RANK_HISTORY_FILE.exists():
        with RANK_HISTORY_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"history": []}


def update_rank_history(date: str, ranks: dict) -> dict:
    """그날의 순위 스냅샷을 이력에 남긴다(같은 날짜 재실행은 덮어씀, 날짜순 정렬).
    이 이력으로 '전일 대비 변동'과 '어떤 매체가 1위를 며칠 유지했나'를 계산한다."""
    hist = load_rank_history()
    entries = [e for e in hist.get("history", []) if e.get("date") != date]
    entries.append({"date": date, "ranks": ranks})
    entries.sort(key=lambda e: e["date"])
    hist["history"] = entries
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    with RANK_HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
    return hist


def save_article_report(date: str, records: list[dict]) -> None:
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    penalized = [r for r in records if r.get("points", 0) > 0]
    total_points = sum(r.get("points", 0) for r in records)
    payload = {
        "date": date,
        "scored": len(records),
        "penalized_count": len(penalized),
        "total_points": total_points,
        "density_per_1000": (total_points / len(records) * 1000) if records else 0.0,
        "attribution_total": sum(r.get("attribution", 0) for r in records),
        "outlier_total": sum(1 for r in records if r.get("outlier")),
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
        flags = outlier_flags(articles)
        records = []
        for a in articles:
            ch = {"title": a.get("title", ""), "lead": a.get("summary", ""), "body": ""}
            r = score_article(ch)
            records.append({
                "source": a.get("source", ""),
                "category": a.get("category", ""),
                "title": a.get("title", ""),
                "link": a.get("link", ""),
                "score": r["score"],
                "points": r["points"],
                "hits": r["hits"],
                "attribution": attribution_count(ch),
                "outlier": bool(flags.get(a.get("link", ""))),
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
    if dates:
        update_rank_history(dates[-1], compute_ranks(store))
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
    update_rank_history(date, compute_ranks(store))

    print(f"=== 객관성 감점 밀도 ({date}) — 낮을수록 객관적 ===")
    for source, m in sorted(store["media"].items(),
                            key=lambda kv: kv[1].get("density_per_1000", 0), reverse=True):
        print(f"  {m.get('density_per_1000', 0):7.1f}/1k · {source} "
              f"(표본 {m['count']}, 인용 {m.get('attribution_total',0)}, "
              f"이상치 {m.get('outlier_total',0)})")
    print(f"저장됨: {MEDIA_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
