"""매체 선택률·본문 점수 유틸 (curate 파이프라인이 소비).

- score_article/body_objectivity: 낚시 게이트·본문 객관성 점수(제목+본문 감점 휴리스틱)
- representative_score/title_penalty/source_coverage: 대표 선정 결합 점수
- update_selection_rates/compute_selection_ranks/update_rank_history: 선택률(win/appear,
  전역+분야별) 누적·순위. curate가 라이브 실행에서 호출·영속화한다(observe-only).

감점 사전 시드: AI_CONTEXT.md §6 "피해야 할 표현".
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from curate import INSTITUTIONS, evidence_signals  # 증거신호·기관목록 재사용(격리: 단방향 의존)

ROOT = Path(__file__).resolve().parent.parent
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
# 귀속표지: "누가 밝혔나"(출처 명시). 자기지칭어: 자화자찬(자기 보고서 인용) 신호.
_SOURCE_MARKERS = re.compile(
    r"에 따르면|밝혔다|말했다|전했다|설명했다|강조했다|덧붙였다|지적했다|분석했다|기술했다|부연|집계됐|발표")
_SELF_REF = re.compile(r"회사|그룹|자사|보고서|기업")


def source_coverage(body: str) -> float:
    """본문 문장 중 '독립 출처를 명시한' 문장 비율(0~1). 단순 수치가 아니라 '누가 밝혔나'를 잰다.
    독립기관(통계청 등) 인용은 자기인용과 무관하게 인정, 귀속표지는 자기지칭어가 없을 때만 인정.
    → 보도자료 자기인용은 근거로 안 침(홍보 기사 근거성 0)."""
    sents = [s for s in _SENT_SPLIT.split(body) if s.strip()]
    if not sents:
        return 0.0

    def sourced(s: str) -> bool:
        if any(inst in s for inst in INSTITUTIONS):
            return True
        return bool(_SOURCE_MARKERS.search(s)) and not _SELF_REF.search(s)

    return sum(1 for s in sents if sourced(s)) / len(sents)


# ponytail: 라벨 2개 보정 시드값. 16=medium 2건 → 객관성 0(=medium 1건이면 정확히 0.5).
# 데이터 축적 후 tier 가중치와 함께 재보정.
OBJ_PENALTY_FULL = 16


def title_penalty(title: str) -> float:
    """제목 편파·낚시 감점(scope:title 낚시 룰 + 제목에 걸린 평가·전망 룰). 대표 게이트용.
    >0 이면 편파적 제목 = 대표로 안 뽑는다(본문은 채점 total로 별도 판정)."""
    return body_objectivity("", title)["points"]


def representative_score(title: str, body: str) -> dict:
    """대표 선정용 결합 점수. 총합 = 0.6*객관성 + 0.4*근거성.
    객관성 = 감점(제목+본문) 반전(1 - min(감점,16)/16), 근거성 = 독립 출처 커버리지."""
    points = body_objectivity(body, title)["points"]
    objectivity = 1 - min(points, OBJ_PENALTY_FULL) / OBJ_PENALTY_FULL
    coverage = source_coverage(body)
    return {"objectivity": objectivity, "coverage": coverage,
            "total": 0.6 * objectivity + 0.4 * coverage}


def update_selection_rates(store: dict, daily_stats: list[dict], date: str) -> dict:
    """교차검증 클러스터의 멤버 등장·대표 승리를 매체별로 누적(날짜 멱등).
    전역 selection_rate = win/appear + 분야별(by_category) 동일 누적. 생짜 비율(소표본 보정 없음).
    단독 클러스터는 호출부에서 제외."""
    if date in store.get("selection_dates", []):
        return store
    media = store.setdefault("media", {})
    for cl in daily_stats:
        cat = cl.get("category", "")
        for src in cl["members"]:
            m = media.setdefault(src, {})
            m["appear_total"] = m.get("appear_total", 0) + 1
            bc = m.setdefault("by_category", {}).setdefault(cat, {})
            bc["appear_total"] = bc.get("appear_total", 0) + 1
        w = media.setdefault(cl["winner"], {})
        w["win_total"] = w.get("win_total", 0) + 1
        wbc = w.setdefault("by_category", {}).setdefault(cat, {})
        wbc["win_total"] = wbc.get("win_total", 0) + 1
    for m in media.values():
        appear = m.get("appear_total", 0)
        m["selection_rate"] = (m.get("win_total", 0) / appear) if appear else None
        for bc in m.get("by_category", {}).values():
            a = bc.get("appear_total", 0)
            bc["selection_rate"] = (bc.get("win_total", 0) / a) if a else None
    store.setdefault("selection_dates", []).append(date)
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


def compute_selection_ranks(store: dict) -> dict:
    """파이프라인 서열 + rank-history: 선택률(win/appear) 내림차순으로 1위부터(높을수록 우선).
    대표 동점 tie-break·백필 로테이션·브리핑 순위에 쓴다. 선택률 미축적(첫날) 매체는 0으로
    취급 → 매체명 안정정렬(사실상 무순), 최신순 tie-break이 이어받는다(D7).
    등장 이력(appear_total>0)이 있는 매체만 순위에 넣는다."""
    media = store.get("media", {})
    ranked = sorted(
        (s for s, m in media.items() if m.get("appear_total", 0) > 0),
        key=lambda s: (-(media[s].get("selection_rate") or 0.0), s),
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


