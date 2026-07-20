"""Day 3: 선별/중복 제거 모듈.

raw/YYYY-MM-DD.json(수집 결과)을 입력으로 받아
  1) 날짜 필터: 오늘·어제(KST) 기사만 통과
  2) 증거 점수: 숫자/%/기관명/인용/기간표현 휴리스틱(AI 미사용, 기록용 메타데이터)
  3) 중복 제거 + 교차검증: 제목 유사도로 같은 사건 묶고 독립 매체 수 집계
  4) 분야별 상한만큼 선택: (교차검증수↓, 코어단어 포함, 가중치합↓, 발행최신순)
     대표는 본문 채점(객관성 0.6 + 근거성 0.4)으로 뽑는다. 매체 수동 우선순위는 폐지됨.
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
from core_words import extract_core_words, tokenize

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.yaml"
RAW_DIR = ROOT / "raw"
SELECTED_DIR = ROOT / "selected"
SCORES_DIR = ROOT / "scores"
LIMITS_FILE = ROOT / "limits.yaml"

KST = timezone(timedelta(hours=9))
SIMILARITY_THRESHOLD = 0.6  # 제목 유사도 중복 판정 기준
MIN_MEDIA = 3  # 대표 후보 최소 보도 매체 수(교차검증). 미만은 드롭 — 억지로 안 채움(로드맵 §8)

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


def load_source_names(path: Path) -> set[str]:
    """sources.yaml에 등록된 매체명 집합."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {s["매체명"] for sources in data.values() for s in sources}


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
    """제목에 든 코어단어 집합. 토큰 단위 매칭(부분문자열 오탐 방지 — D2③)."""
    toks = tokenize(title)
    return frozenset(w for w in core_words if w in toks)


def _effective_ratio(a: tuple, b: tuple) -> float:
    """유효 유사도 = 실 제목유사도 + 0.15*공유 코어단어수. a,b = (정규화제목, 코어단어집합)."""
    # D3: 가산은 코어단어 1개어치로 상한. 코어단어는 유사도의 보조 신호이지 주신호가
    # 아니다(스펙 §5.1). 상한이 없으면 서술어 2개만 겹쳐도 유사도 0을 병합으로 밀어올림.
    bonus = min(CORE_WORD_BONUS * len(a[1] & b[1]), CORE_WORD_BONUS)
    return SequenceMatcher(None, a[0], b[0]).ratio() + bonus


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


LENGTH_MIN, LENGTH_MAX = 300, 2000   # 대표 후보 본문 길이 범위(벗어나면 제외·기록)
# 상한 2000 = extract.MAX_CHARS(요약 입력 clamp)와 정렬. 도달 기사 p75≈1478·p90≈1933이라
# 1500은 정상 기사 상위 24%를 떨궜다(2026-07-18 분포 확인). 2000↑(8%)만 목록성으로 배제.


def record_representative_strike(rep_data: dict, item: dict, body, date: str) -> bool:
    """멤버 본문 품질(empty/sparse)을 판정해 기자 스트라이크를 기록. 기록했으면 True.
    author 없으면 skip. 정상 본문(≥200자)은 무기록. reporters.record_strike로 날짜·링크 멱등."""
    if not item.get("author"):
        return False
    reason = reporters.classify_body(body)
    if not reason:
        return False
    reporters.record_strike(rep_data, item["source"], item["author"], date,
                            item["link"], reason, 0 if body is None else len(body))
    return True


# 대표 후보 본문 점수 관찰선. 관찰 모드: 이 밑이면 로그만 남기고 배제하지 않는다.
# 라벨(예시1호 total≈0.8·감점1호 0.3)이 2개뿐이라 임의 하한으로 진짜 기사를 떨구는
# 대신, 며칠 분포를 관찰한 뒤 하드 하한으로 승격한다.
# ponytail: observe-only 시드값, 라벨 축적 후 하드 게이트로 전환.
REP_SCORE_FLOOR = 0.35


def _rep_gate_reason(m: dict, body: str, blacklist: set, title_penalty_fn,
                     min_len: int, max_len: int):
    """대표 후보 하드 게이트: 배제 사유 문자열 or None. 길이 → 블랙리스트 → 제목 낚시.
    배제돼도 멤버는 클러스터에 남아 교차검증엔 기여한다(대표 자격만 잃음)."""
    n = len(body)
    if n < min_len or n > max_len:
        return f"length:{n}"
    if reporters.reporter_key(m.get("source", ""), m.get("author", "")) in blacklist:
        return "blacklist"
    if title_penalty_fn and title_penalty_fn(m.get("title", "")) > 0:
        return "clickbait"
    return None


def pick_representative(cluster: dict, extract_fn, score_fn, ranks: dict,
                        excluded: list, blacklist: set = None, title_penalty_fn=None,
                        min_len: int = LENGTH_MIN, max_len: int = LENGTH_MAX, on_body=None):
    """클러스터 멤버 본문을 추출→하드 게이트→score_fn 총합 최고를 대표 멤버로.

    하드 게이트(대표 자격 박탈): 길이 300~1500 이탈 · 블랙리스트 기자 · 제목 낚시(감점>0).
    관찰 게이트(로그만, 배제 안 함): 게이트 통과 대표 후보 전원의 본문 점수를 기록
    (reason=score_observed, 하한 미달은 low_score_observed) — 하드 하한값을 정하려면
    미달만이 아니라 점수 분포 전체가 필요하기 때문.
    유효 멤버가 없으면 None(클러스터 탈락). 배제·관찰 모두 excluded에 reason·title과 함께 기록.
    동점은 매체 density 순위(낮을수록 우선). on_body는 추출 직후 호출(기자 스트라이크 판정).
    extract_fn/score_fn/title_penalty_fn 주입으로 테스트는 네트워크 불필요.
    """
    blacklist = blacklist or set()
    scored = []
    for m in cluster["members"]:
        body = extract_fn(m["link"], m.get("title", "")) or ""
        if on_body is not None:
            on_body(m, body)
        reason = _rep_gate_reason(m, body, blacklist, title_penalty_fn, min_len, max_len)
        if reason:
            excluded.append({"source": m.get("source", ""), "link": m["link"],
                             "reason": reason, "title": m.get("title", ""),
                             "category": m.get("category", "")})
            continue
        sc = score_fn(m.get("title", ""), body)
        # 관찰 모드: 통과 후보 전원의 점수를 기록(분포 확인용). 배제는 안 함.
        excluded.append({"source": m.get("source", ""), "link": m["link"],
                         "reason": "low_score_observed" if sc["total"] < REP_SCORE_FLOOR
                                   else "score_observed",
                         "score": round(sc["total"], 3), "title": m.get("title", ""),
                         "category": m.get("category", "")})
        rank = ranks.get(m.get("source", ""), 10 ** 9)
        # tie-break: 점수 → 선택률 순위(rank↓) → 최신순(D7). recency_key는 -ts라 부호 반전.
        scored.append(((sc["total"], -rank, -recency_key(m.get("published_iso", ""))), m))
    if not scored:
        return None
    return max(scored, key=lambda t: t[0])[1]


def _apply_representative(cluster: dict, rep: dict) -> dict:
    """클러스터의 대표를 body 채점 승자(rep)로 교체하고 members는 뺀다(선정 결과 경량화)."""
    c = {k: v for k, v in cluster.items() if k != "members"}
    c.update({"title": rep["title"], "link": rep["link"], "source": rep["source"],
              "published_iso": rep.get("published_iso", c.get("published_iso", "")),
              "summary": rep.get("summary", ""), "author": rep.get("author", "")})
    c["related_links"] = [{"source": m["source"], "link": m["link"]}
                          for m in cluster["members"] if m["link"] != rep["link"]]
    return c


def select(raw: dict, today: datetime,
           default_limit: int = 2, per_category_limits: dict = None,
           extract_fn=None, score_fn=None,
           ranks: dict = None, on_body=None,
           blacklist: set = None, title_penalty_fn=None) -> dict:
    """score_fn 주입 시: 최소 3매체 통과분만 매체 다양성순으로, 대표는 본문 채점+게이트로.
    미주입 시 기존 동작(정렬 후 상한 슬라이스, 본문 미검증 — 카운트 테스트용)."""
    if per_category_limits is None:
        per_category_limits = {}
    ranks = ranks or {}
    categories: dict[str, list[dict]] = {}
    stats: dict[str, dict] = {}
    excluded: list[dict] = []
    selection_stats: list[dict] = []   # 교차검증 클러스터 평판 갱신용(멤버 등장·대표 승리)

    # 분야별로 기사 모으기
    by_cat: dict[str, list[dict]] = {}
    for art in raw["articles"]:
        by_cat.setdefault(art["category"], []).append(art)

    for category, arts in by_cat.items():
        dated = [a for a in arts if in_date_window(a, today)]
        cwords = extract_core_words([a["title"] for a in dated])
        clusters = cluster_articles(dated, cwords)
        # 정렬(D8): 매체 다양성↓ → 최신순. 코어단어 가중치는 관찰용이라 정렬서 뺐다.
        clusters.sort(
            key=lambda c: (-c["corroboration_count"], recency_key(c["published_iso"]))
        )
        limit = per_category_limits.get(category, default_limit)
        if score_fn is None:
            selected = clusters[:limit]                               # 본문 미검증(기존 동작)
        else:
            # 최소 3매체 통과분만, 상위 limit개. 부족하면 그대로 둔다(백필 없음).
            selected = []
            for c in clusters:
                if len(selected) >= limit:
                    break
                if c["corroboration_count"] < MIN_MEDIA:
                    continue
                rep = pick_representative(c, extract_fn, score_fn, ranks, excluded,
                                          blacklist=blacklist, title_penalty_fn=title_penalty_fn,
                                          on_body=on_body)
                if rep is not None:                                   # 유효 대표 없으면 클러스터 탈락
                    selected.append(_apply_representative(c, rep))
                    selection_stats.append({
                        "members": [m["source"] for m in c["members"]],
                        "winner": rep["source"]})
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
        "gate_excluded": excluded,
        "selection_stats": selection_stats,
    }


def save(result: dict) -> Path:
    SELECTED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SELECTED_DIR / f"{result['date']}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return out_path


def main(date: str = None, dry_run: bool = False) -> int:
    if date is None:
        date = datetime.now(KST).strftime("%Y-%m-%d")
    try:
        raw = load_raw(date)
    except FileNotFoundError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    # objectivity는 curate를 import하므로 순환 회피 위해 지역 import.
    import core_words
    import objectivity
    from extract import extract_body

    default_limit, per_category_limits = load_limits(LIMITS_FILE)
    # 블랙리스트는 pool 선제거가 아니라 대표 게이트에서 적용(D5) — 블랙 기자 기사도
    # 클러스터 멤버로 남아 교차검증에 기여하되, 대표로만 안 뽑힌다.
    blacklist = reporters.blacklisted_keys(reporters.load())
    today = datetime.now(KST)

    # 코어단어 주제·가중치(관찰 + 정렬 tiebreak) — 선별 전에 갱신해 그날 정렬에 반영.
    dated_all = [a for a in raw["articles"] if in_date_window(a, today)]
    cwords = extract_core_words([a["title"] for a in dated_all])
    top3 = core_words.top_topics(core_words.core_word_stats(dated_all, cwords), 3)
    wstore = core_words.load_weights()
    core_words.update_core_weights(wstore, top3, date)   # 메모리 갱신(이번 정렬 반영)
    if not dry_run:                                       # 상태 영속화는 dry-run에서 생략
        core_words.record_topics(date, top3)
        core_words.save_weights(wstore)

    # 파이프라인 서열 = 선택률 순위(D6). density는 브리핑 관찰축으로만 유지(여기 미사용).
    store = objectivity.load_store()
    ranks = objectivity.compute_selection_ranks(store)
    # 기자 부실 스트라이크: 대표 후보 본문 판정 시점(선별)에 기록(요약 단계에서 이동).
    rep_data = reporters.load()
    on_body = lambda m, body: record_representative_strike(rep_data, m, body, date)  # noqa: E731
    result = select(raw, today, default_limit, per_category_limits,
                    extract_fn=extract_body,
                    score_fn=objectivity.representative_score, ranks=ranks, on_body=on_body,
                    blacklist=blacklist, title_penalty_fn=objectivity.title_penalty)
    out_path = save(result)   # selected/ 는 gitignore 산출물 — dry-run에서도 기록(체이닝·검수용)

    if not dry_run:
        reporters.save(rep_data)
        # 선택률 평판 갱신(교차검증 클러스터 부산물, 날짜 멱등).
        objectivity.update_selection_rates(store, result["selection_stats"], date)
        objectivity.save_store(store)
    else:
        print("  [dry-run] scores/ 상태 미기록 (media.json·가중치·평판·주제 보존)")

    # gate-excluded는 날짜 멱등한 관찰 스냅샷(누적 상태 아님) — 하한값 관찰용이라 dry-run에서도 기록.
    if result["gate_excluded"]:
        excl_path = SCORES_DIR / f"gate-excluded-{date}.json"
        SCORES_DIR.mkdir(parents=True, exist_ok=True)
        with excl_path.open("w", encoding="utf-8") as f:
            json.dump({"date": date, "excluded": result["gate_excluded"]},
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
    _args = sys.argv[1:]
    _dry = "--dry-run" in _args
    _rest = [a for a in _args if a != "--dry-run"]
    raise SystemExit(main(_rest[0] if _rest else None, dry_run=_dry))
