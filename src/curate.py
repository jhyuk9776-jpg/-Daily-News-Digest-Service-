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

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.yaml"
RAW_DIR = ROOT / "raw"
SELECTED_DIR = ROOT / "selected"

KST = timezone(timedelta(hours=9))
PER_CATEGORY = 2            # 분야별 선택 건수 (기획 확정값)
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


def evidence_score(article: dict) -> int:
    """제목+요약에서 증거 신호 개수를 센다(AI 미사용)."""
    text = f"{article.get('title', '')} {article.get('summary', '')}"
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


def cluster_articles(articles: list[dict], priority_map: dict) -> list[dict]:
    """같은 사건끼리 묶어 클러스터 리스트를 만든다.

    각 클러스터: 대표 기사 + 교차검증수(독립 매체 수) + 관련 링크 + 증거점수.
    """
    clusters: list[dict] = []
    for art in articles:
        norm = normalize_title(art["title"])
        placed = False
        for cl in clusters:
            if SequenceMatcher(None, norm, cl["_norm"]).ratio() >= SIMILARITY_THRESHOLD:
                cl["members"].append(art)
                placed = True
                break
        if not placed:
            clusters.append({"_norm": norm, "members": [art]})

    result = []
    for cl in clusters:
        members = cl["members"]
        # 대표 기사: 우선순위 최상위(숫자 작은 값)
        rep = min(members, key=lambda a: priority_map.get((a["category"], a["source"]), 99))
        sources = {m["source"] for m in members}
        related = [
            {"source": m["source"], "link": m["link"]}
            for m in members
            if m["link"] != rep["link"]
        ]
        result.append(
            {
                "title": rep["title"],
                "link": rep["link"],
                "source": rep["source"],
                "published": rep.get("published", ""),
                "published_iso": rep.get("published_iso", ""),
                "date_known": rep.get("date_known", True),
                "summary": rep.get("summary", ""),
                "evidence_score": max(evidence_score(m) for m in members),
                "corroboration_count": len(sources),
                "related_links": related,
            }
        )
    return result


def select(raw: dict, priority_map: dict, today: datetime) -> dict:
    categories: dict[str, list[dict]] = {}
    stats: dict[str, dict] = {}

    # 분야별로 기사 모으기
    by_cat: dict[str, list[dict]] = {}
    for art in raw["articles"]:
        by_cat.setdefault(art["category"], []).append(art)

    for category, arts in by_cat.items():
        dated = [a for a in arts if in_date_window(a, today)]
        clusters = cluster_articles(dated, priority_map)
        clusters.sort(
            key=lambda c: (
                -c["corroboration_count"],                       # 1순위: 여러 매체가 보도할수록 위로
                priority_map.get((category, c["source"]), 99),   # 2순위: 매체 우선순위 높을수록 위로
                recency_key(c["published_iso"]),                 # 3순위: 발행 최신순(동점 시 임의성 제거)
            )
        )
        selected = clusters[:PER_CATEGORY]
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

    priority_map = load_priority_map(SOURCES_FILE)
    today = datetime.now(KST)
    result = select(raw, priority_map, today)
    out_path = save(result)

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
