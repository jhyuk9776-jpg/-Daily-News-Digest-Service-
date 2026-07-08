"""기자 부실 스트라이크 축적 (본문 없음/부실 반복 기자 감지·제외).

매체 평판(scores/media.json)이 '매체' 단위라면, 이 모듈은 '기자' 단위 부실 이력을
scores/reporters.json에 누적한다. 점수 3점 도달 시 blacklisted=true가 되고,
curate가 해당 기자 기사를 선별 후보에서 제외한다.

설계: docs/superpowers/specs/2026-07-08-부실기사-기자블랙리스트-design.md
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTERS_FILE = ROOT / "scores" / "reporters.json"

SPARSE_MIN_CHARS = 200   # 본문 길이가 이 값 미만이면 '부실'
SPARSE_TO_POINT = 3      # 부실 카운트가 이 값에 도달하면 1점으로 승격
BLACKLIST_POINTS = 3     # 누적 점수가 이 값 이상이면 블랙리스트


def normalize_author(name: str) -> str:
    """기자명 정규화: 앞뒤 공백 제거 + 끝의 '기자' 접미사 제거."""
    n = name.strip()
    if n.endswith("기자"):
        n = n[:-2].strip()
    return n


def reporter_key(source: str, author: str) -> str:
    """'{매체}::{정규화된 기자명}' 키."""
    return f"{source}::{normalize_author(author)}"


def classify_body(body: str | None) -> str | None:
    """대표 기사 본문 품질을 판정한다. 'empty' | 'sparse' | None(정상)."""
    if body is None:
        return "empty"
    if len(body) < SPARSE_MIN_CHARS:
        return "sparse"
    return None


def load() -> dict:
    if not REPORTERS_FILE.exists():
        return {}
    with REPORTERS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save(data: dict) -> None:
    REPORTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with REPORTERS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def blacklisted_keys(data: dict) -> set[str]:
    return {k for k, v in data.items() if v.get("blacklisted")}


def record_strike(data: dict, source: str, author: str, date: str,
                  link: str, reason: str, chars: int) -> dict:
    """대표 기사 판정 결과(reason='empty'|'sparse')를 기자 이력에 반영한다.

    같은 (date, link)가 이미 있으면 no-op(이중 감점 금지). 갱신된 data를 반환한다.
    """
    key = reporter_key(source, author)
    rec = data.setdefault(
        key, {"sparse_count": 0, "points": 0, "blacklisted": False,
              "last_updated": "", "history": []},
    )
    if any(h["date"] == date and h["link"] == link for h in rec["history"]):
        return data

    rec["history"].append({"date": date, "link": link, "reason": reason, "chars": chars})
    rec["last_updated"] = date
    if reason == "empty":
        rec["points"] += 1
    elif reason == "sparse":
        rec["sparse_count"] += 1
        if rec["sparse_count"] >= SPARSE_TO_POINT:
            rec["points"] += 1
            rec["sparse_count"] = 0
    if rec["points"] >= BLACKLIST_POINTS:
        rec["blacklisted"] = True
    return data
