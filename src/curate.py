"""Day 3: 선별/중복 제거 모듈.

raw/YYYY-MM-DD.json(수집 결과)을 입력으로 받아
  1) 날짜 필터: 오늘·어제(KST) 기사만 통과
  2) 증거 점수: 숫자/%/기관명/인용/기간표현 휴리스틱(AI 미사용, 기록용 메타데이터)
  3) 중복 제거 + 교차검증: 제목 유사도로 같은 사건 묶고 독립 매체 수 집계
  4) 분야별 상위 2건 선택: (교차검증수↓, 우선순위↑, 발행최신순)
결과를 selected/YYYY-MM-DD.json 으로 저장한다(Day 4 입력).

증거 우선 전략은 기획/04-decision-log.md "1.1 증거 기반 품질 전략" 참고.

실행:
    python3 src/select.py            # raw/<오늘>.json 사용
    python3 src/select.py 2026-06-30 # 특정 날짜 지정
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

import yaml

import reporters
from core_words import extract_core_words, load_weights, weight_of

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.yaml"
RAW_DIR = ROOT / "raw"
SELECTED_DIR = ROOT / "selected"
SCORES_DIR = ROOT / "scores"
LIMITS_FILE = ROOT / "limits.yaml"

KST = timezone(timedelta(hours=9))
SIMILARITY_THRESHOLD = 0.6  # 제목 유사도 중복 판정 기준

# 증거 신호: 공신력 있는 기관명 (있으면 가점)
INSTITUTIONS = [
    "통계청", "한국은행", "기획재정부", "기재부", "금융위", "금융감독원", "금감원",
    "대법원", "헌법재판소", "검찰", "경찰청", "국세청", "고용노동부", "산업통상자원부",
    "국토교통부", "보건복지부", "질병관리청", "공정거래위", "감사원", "국회", "정부",
    "OECD", "IMF", "WHO", "UN", "세계은행", "연준", "Fed", "ECB",
]
# 기간/비교 표현 (통계적 사실의 단서)
PERIOD_PATTERN = re.compile(r"전년\s*대비|전월\s*대비|전분기|분기|올해|지난해|작년|상반기|하반기")
NUMBER_PATTERN = re.compile(r"\d")
QUOTE_PATTERN = re.compile(r"[\"'“”‘’]")


def load_priority_map(path: Path) -> dict[tuple[str, str], int]:
    """(분야, 매체명) -> 우선순위 매핑을 만든다."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    mapping: dict[tuple[str, str], int] = {}
    for category, sources in data.items():
        for s in sources:
            mapping[(category, s["매체명"])] = s.get("우선순위", 99)
    return mapping


def load_limits(path: Path):
    """분야별 요약 상한을 읽는다. 반환 (default_limit, per_category_limits).

    파일이 없거나 비어 있으면 (2, {})로 폴백해 기존 동작(분야별 2건)을 유지한다.
    """
    if not path.exists():
        return 2, {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    default = data.get("default", 2)
    per_category = data.get("per_category", {}) or {}
    return default, per_category


def load_raw(date: str) -> dict:
    path = RAW_DIR / f"{date}.json"
    if not path.exists():
        raise FileNotFoundError(f"수집 결과가 없음: {path} (먼저 fetch.py 실행)")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def filter_blacklisted(articles: list[dict], blacklist: set[str]) -> list[dict]:
    """블랙리스트 (매체,기자) 기사를 후보에서 제거한다.

    author 필드가 없거나 빈 기사는 키가 블랙리스트에 없으므로 통과한다(안전).
    """
    if not blacklist:
        return articles
    return [
        a for a in articles
        if reporters.reporter_key(a["source"], a.get("author", "")) not in blacklist
    ]


def in_date_window(article: dict, today: datetime) -> bool:
    """오늘·어제(KST) 기사인지 판정. 날짜 없으면 통과(date_known=False로 표시)."""
    iso = article.get("published_iso", "")
    if not iso:
        article["date_known"] = False
        return True
    try:
        dt = datetime.fromisoformat(iso).astimezone(KST)
    except ValueError:
        article["date_known"] = False
        return True
    article["date_known"] = True
    delta_days = (today.date() - dt.date()).days
    return 0 <= delta_days <= 1


def evidence_signals(text: str) -> int:
    """텍스트에서 증거 신호 개수를 센다(숫자·%·기관·인용·기간, AI 미사용, 0~5)."""
    score = 0
    if NUMBER_PATTERN.search(text):
        score += 1
    if "%" in text or "퍼센트" in text:
        score += 1
    if any(inst in text for inst in INSTITUTIONS):
        score += 1
    if QUOTE_PATTERN.search(text):
        score += 1
    if PERIOD_PATTERN.search(text):
        score += 1
    return score


def evidence_score(article: dict) -> int:
    """제목+요약의 증거 신호 개수(기존 호출부 호환 래퍼)."""
    return evidence_signals(f"{article.get('title', '')} {article.get('summary', '')}")


def recency_key(iso: str) -> float:
    """정렬용 최신순 키: 최신일수록 작은 값(오름차순 정렬에서 위로 온다).

    발행일을 모르는 기사(iso 빈 값/파싱 실패)는 0.0을 돌려 맨 뒤로 보낸다.
    """
    if not iso:
        return 0.0
    try:
        return -datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return 0.0


def normalize_title(title: str) -> str:
    """중복 비교용 제목 정규화: 대괄호 머리표·기호 제거, 공백 정리."""
    t = re.sub(r"\[[^\]]*\]", " ", title)       # [속보] [단독] 류 제거
    t = re.sub(r"[^\w가-힣]", " ", t)            # 기호 제거
    return re.sub(r"\s+", " ", t).strip().lower()


CORE_WORD_BONUS = 0.15   # 코어단어 1개 공유당 유사도 가산(과병합 방지 위해 소폭)


def _title_cores(title: str, core_words) -> frozenset:
    """제목에 든 코어단어 집합."""
    return frozenset(w for w in core_words if w in title)


def _effective_ratio(a: tuple, b: tuple) -> float:
    """유효 유사도 = 실 제목유사도 + 0.15*공유 코어단어수. a,b = (정규화제목, 코어단어집합)."""
    return SequenceMatcher(None, a[0], b[0]).ratio() + CORE_WORD_BONUS * len(a[1] & b[1])


def _greedy_clusters(keys: list, threshold: float = SIMILARITY_THRESHOLD) -> list:
    """keys=[(norm,cores)...]를 유효유사도 threshold로 그리디 병합. 클러스터별 인덱스 리스트."""
    clusters: list = []  # [(key, [idx,...]), ...]
    for i, k in enumerate(keys):
        for key, idx in clusters:
            if _effective_ratio(k, key) >= threshold:
                idx.append(i)
                break
        else:
            clusters.append((k, [i]))
    return [idx for _, idx in clusters]


def _newest(arts: list[dict]) -> dict:
    """발행 최신 기사(recency_key가 작을수록 최신)."""
    return min(arts, key=lambda a: recency_key(a.get("published_iso", "")))


def cluster_articles(articles: list[dict], core_words=None) -> list[dict]:
    """2단계 클러스터링. core_words=None이면 제목에서 자동 추출.

    1차(같은 매체 내부): 유사도+코어단어로 묶고 최근 1건만 유지(나머지는 개수로만).
    2차(매체 간): 1차 생존자를 교차 클러스터링 → 교차검증수(독립 매체 수) 집계.
    """
    if core_words is None:
        core_words = extract_core_words([a["title"] for a in articles])

    # 1차: 매체 내부 병합 → 최근 1건 (survivors: [(대표기사, 붕괴전 개수), ...])
    survivors: list = []
    by_source: dict[str, list] = {}
    for a in articles:
        by_source.setdefault(a.get("source", ""), []).append(a)
    for arts in by_source.values():
        keys = [(normalize_title(a["title"]), _title_cores(a["title"], core_words)) for a in arts]
        for idx in _greedy_clusters(keys):
            group = [arts[i] for i in idx]
            survivors.append((_newest(group), len(group)))

    # 2차: 매체 간 병합
    keys = [(normalize_title(s[0]["title"]), _title_cores(s[0]["title"], core_words))
            for s in survivors]
    result = []
    for idx in _greedy_clusters(keys):
        members = [survivors[i][0] for i in idx]
        intra_total = sum(survivors[i][1] for i in idx)
        rep = _newest(members)
        sources = {m.get("source", "") for m in members}
        result.append({
            "title": rep["title"],
            "link": rep["link"],
            "source": rep["source"],
            "published": rep.get("published", ""),
            "published_iso": rep.get("published_iso", ""),
            "date_known": rep.get("date_known", True),
            "summary": rep.get("summary", ""),
            "author": rep.get("author", ""),
            "evidence_score": max(evidence_score(m) for m in members),
            "corroboration_count": len(sources),
            "article_total": intra_total,             # 붕괴 전 총 기사 수(중요도 신호)
            "core_words": sorted(_title_cores(rep["title"], core_words)),
            "members": members,                       # Phase 4 본문 채점용
            "related_links": [{"source": m["source"], "link": m["link"]}
                              for m in members if m["link"] != rep["link"]],
        })
    return result


LENGTH_MIN, LENGTH_MAX = 300, 1500   # 대표 후보 본문 길이 범위(벗어나면 제외·기록)


def pick_representative(cluster: dict, extract_fn, score_fn, ranks: dict,
                        excluded: list, min_len: int = LENGTH_MIN,
                        max_len: int = LENGTH_MAX):
    """클러스터 멤버 본문을 추출→길이필터(300~1500)→score_fn 총합 최고를 대표 멤버로.

    유효 길이 멤버가 없으면 None(클러스터 탈락). 길이 이탈 멤버는 excluded에 기록.
    동점은 매체 density 순위(낮을수록 우선). extract_fn/score_fn 주입으로 테스트는 네트워크 불필요.
    """
    scored = []
    for m in cluster["members"]:
        body = extract_fn(m["link"], m.get("title", "")) or ""
        n = len(body)
        if n < min_len or n > max_len:
            excluded.append({"source": m.get("source", ""), "link": m["link"],
                             "length": n, "category": m.get("category", "")})
            continue
        rank = ranks.get(m.get("source", ""), 10 ** 9)
        scored.append(((score_fn(m.get("title", ""), body)["total"], -rank), m))
    if not scored:
        return None
    return max(scored, key=lambda t: t[0])[1]


def backfill_round_robin(solo: list[dict], ranks: dict, need: int) -> list[dict]:
    """상한 미달 시 단독 클러스터로 채운다. 매체 density 상위 3곳만 라운드로빈(1·2·3·1·2·3…).

    각 매체 내부는 최신순. 상위 3곳 소진 시 need 미달이어도 멈춘다(그 매체들만 사용).
    """
    top3 = sorted((s for s in ranks), key=lambda s: ranks[s])[:3]
    by_src: dict[str, list] = {s: [] for s in top3}
    for c in solo:
        if c.get("source", "") in by_src:
            by_src[c["source"]].append(c)
    for s in top3:
        by_src[s].sort(key=lambda c: recency_key(c.get("published_iso", "")))
    out: list = []
    while len(out) < need and any(by_src[s] for s in top3):
        for s in top3:
            if by_src[s]:
                out.append(by_src[s].pop(0))
                if len(out) >= need:
                    break
    return out


def _apply_representative(cluster: dict, rep: dict) -> dict:
    """클러스터의 대표를 body 채점 승자(rep)로 교체하고 members는 뺀다(선정 결과 경량화)."""
    c = {k: v for k, v in cluster.items() if k != "members"}
    c.update({"title": rep["title"], "link": rep["link"], "source": rep["source"],
              "published_iso": rep.get("published_iso", c.get("published_iso", "")),
              "summary": rep.get("summary", ""), "author": rep.get("author", "")})
    c["related_links"] = [{"source": m["source"], "link": m["link"]}
                          for m in cluster["members"] if m["link"] != rep["link"]]
    return c


def select(raw: dict, priority_map: dict, today: datetime,
           default_limit: int = 2, per_category_limits: dict = None,
           core_weights: dict = None, extract_fn=None, score_fn=None,
           ranks: dict = None) -> dict:
    """extract_fn·score_fn 주입 시 본문 채점 대표 선정 + 길이필터 + density 백필(Phase 4).
    미주입 시 기존 동작(정렬 후 상한 슬라이스, 본문 미검증)."""
    if per_category_limits is None:
        per_category_limits = {}
    if core_weights is None:
        core_weights = load_weights()
    ranks = ranks or {}
    categories: dict[str, list[dict]] = {}
    stats: dict[str, dict] = {}
    excluded: list[dict] = []

    # 분야별로 기사 모으기
    by_cat: dict[str, list[dict]] = {}
    for art in raw["articles"]:
        by_cat.setdefault(art["category"], []).append(art)

    for category, arts in by_cat.items():
        dated = [a for a in arts if in_date_window(a, today)]
        cwords = extract_core_words([a["title"] for a in dated])
        clusters = cluster_articles(dated, cwords)
        clusters.sort(
            key=lambda c: (
                -c["corroboration_count"],                            # 1순위: 등장 매체 수↓
                0 if c["core_words"] else 1,                          # 2순위: 제목 코어단어 포함 우선
                -sum(weight_of(core_weights, w) for w in c["core_words"]),  # 3순위: 코어단어 가중치 합↓
                recency_key(c["published_iso"]),                      # 4순위: 발행 최신순
            )
        )
        limit = per_category_limits.get(category, default_limit)
        if score_fn is None:
            selected = clusters[:limit]                               # 본문 미검증(기존 동작)
        else:
            # 교차검증 우선 + 부족분 단독 density 3위 라운드로빈 백필, 대표는 본문 채점으로
            corroborated = [c for c in clusters if c["corroboration_count"] >= 2]
            solo = [c for c in clusters if c["corroboration_count"] < 2]
            ordered = corroborated + backfill_round_robin(solo, ranks, limit)
            selected = []
            for c in ordered:
                if len(selected) >= limit:
                    break
                rep = pick_representative(c, extract_fn, score_fn, ranks, excluded)
                if rep is not None:                                   # 유효 길이 멤버 없으면 탈락
                    selected.append(_apply_representative(c, rep))
        categories[category] = selected
        stats[category] = {
            "candidates": len(arts),
            "after_date_filter": len(dated),
            "clusters": len(clusters),
            "selected": len(selected),
        }

    return {
        "date": raw["date"],
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "window": {
            "from": (today.date() - timedelta(days=1)).isoformat(),
            "to": today.date().isoformat(),
        },
        "stats": stats,
        "categories": categories,
        "length_excluded": excluded,
    }


def save(result: dict) -> Path:
    SELECTED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SELECTED_DIR / f"{result['date']}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return out_path


def main() -> int:
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now(KST).strftime("%Y-%m-%d")
    try:
        raw = load_raw(date)
    except FileNotFoundError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    # objectivity는 curate를 import하므로 순환 회피 위해 지역 import.
    import core_words
    import objectivity
    from extract import extract_body

    priority_map = load_priority_map(SOURCES_FILE)
    default_limit, per_category_limits = load_limits(LIMITS_FILE)
    blacklist = reporters.blacklisted_keys(reporters.load())
    raw["articles"] = filter_blacklisted(raw["articles"], blacklist)
    today = datetime.now(KST)

    # 코어단어 주제·가중치(관찰 + 정렬 tiebreak) — 선별 전에 갱신해 그날 정렬에 반영.
    dated_all = [a for a in raw["articles"] if in_date_window(a, today)]
    cwords = extract_core_words([a["title"] for a in dated_all])
    top3 = core_words.top_topics(core_words.core_word_stats(dated_all, cwords), 3)
    core_words.record_topics(date, top3)
    wstore = core_words.load_weights()
    core_words.update_core_weights(wstore, top3, date)
    core_words.save_weights(wstore)

    # density 순위(매체 우선순위 대체) — 백필·동점 tiebreak용.
    ranks = objectivity.compute_ranks(objectivity.load_store())
    result = select(raw, priority_map, today, default_limit, per_category_limits,
                    core_weights=wstore, extract_fn=extract_body,
                    score_fn=objectivity.representative_score, ranks=ranks)
    out_path = save(result)

    if result["length_excluded"]:
        excl_path = SCORES_DIR / f"length-excluded-{date}.json"
        SCORES_DIR.mkdir(parents=True, exist_ok=True)
        with excl_path.open("w", encoding="utf-8") as f:
            json.dump({"date": date, "excluded": result["length_excluded"]},
                      f, ensure_ascii=False, indent=2)

    print(f"=== 선별 결과 ({date}, 창: {result['window']['from']}~{result['window']['to']}) ===")
    for category, items in result["categories"].items():
        st = result["stats"][category]
        print(f"\n[{category}] 수집 {st['candidates']} → 날짜통과 {st['after_date_filter']} "
              f"→ 묶음 {st['clusters']} → 선택 {st['selected']}")
        if not items:
            print("  (해당 분야 새 기사 없음)")
        for it in items:
            flag = "" if it["date_known"] else " (날짜미상)"
            print(f"  - [증거{it['evidence_score']} 교차{it['corroboration_count']}] "
                  f"{it['title'][:45]} / {it['source']}{flag}")
    print(f"\n저장됨: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
