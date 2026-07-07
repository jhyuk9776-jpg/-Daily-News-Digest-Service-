"""트랙2: 다이제스트(선별분) 본문 감사 — 제목+리드+본문 채점.

트랙1(매체 밀도)과 모집단·텍스트 범위가 달라 별도 리포트로 격리한다.
본문은 extract.py로 재추출(BeautifulSoup, AI 비용 0, 최대 ~16건/일).
매체 media.json은 건드리지 않는다(observe-only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import objectivity

ROOT = Path(__file__).resolve().parent.parent
SELECTED_DIR = ROOT / "selected"
SCORES_DIR = ROOT / "scores"


def _iter_selected(payload: dict):
    for _cat, items in payload.get("categories", {}).items():
        for it in items:
            yield it


def audit_digest(date: str, fetch_body, selected_dir: Path = None,
                 scores_dir: Path = None) -> dict:
    selected_dir = SELECTED_DIR if selected_dir is None else Path(selected_dir)
    scores_dir = SCORES_DIR if scores_dir is None else Path(scores_dir)
    payload = json.loads((selected_dir / f"{date}.json").read_text(encoding="utf-8"))

    items = []
    for it in _iter_selected(payload):
        body = fetch_body(it.get("link", "")) or ""
        ch = {"title": it.get("title", ""), "lead": it.get("summary", ""), "body": body}
        r = objectivity.score_article(ch)
        items.append({"source": it.get("source", ""), "title": it.get("title", ""),
                      "link": it.get("link", ""), "score": r["score"],
                      "points": r["points"], "hits": r["hits"]})

    penalized = [i for i in items if i["points"] > 0]
    result = {"date": date, "audited": len(items),
              "penalized_count": len(penalized), "items": penalized}
    scores_dir.mkdir(parents=True, exist_ok=True)
    (scores_dir / f"digest-audit-{date}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _extract_body(url: str) -> str:
    """운영용 본문 추출(extract.py 재사용). 실패 시 빈 문자열."""
    try:
        import extract
        return extract.extract_body(url) or ""
    except Exception as exc:  # 추출 실패는 감사 스킵(치명적 아님)
        print(f"경고: 본문 추출 실패 {url} — {exc}", file=sys.stderr)
        return ""


def main() -> int:
    from datetime import datetime, timedelta, timezone
    kst = timezone(timedelta(hours=9))
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now(kst).strftime("%Y-%m-%d")
    result = audit_digest(date, fetch_body=_extract_body)
    print(f"=== 다이제스트 본문 감사 ({date}) ===")
    print(f"  감사 {result['audited']}건, 감점 {result['penalized_count']}건")
    for i in result["items"]:
        print(f"  -{i['points']:.1f} · {i['source']} · {i['title'][:30]} {i['hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
