"""Day 2: RSS 수집 모듈.

고정된 RSS 출처(sources.yaml)에서 분야별 기사 리스트를 수집해
raw/YYYY-MM-DD.json 으로 저장한다.

이 단계에서는 '가져오기'만 한다.
날짜 필터 / 분야별 추리기 / 중복 제거 / 요약은 하지 않는다 (Day 3, Day 4).

실행:
    python3 src/fetch.py
"""

from __future__ import annotations

import calendar
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml

# 경로 기준: 이 파일의 부모(src)의 부모 = 프로젝트 루트
ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.yaml"
RAW_DIR = ROOT / "raw"

# 일부 서버는 기본 UA를 차단하므로 브라우저 UA를 사용한다.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def load_sources(path: Path) -> dict:
    """sources.yaml 을 읽어 {분야: [출처...]} 형태로 돌려준다."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or not data:
        raise ValueError(f"출처 설정이 비어 있거나 형식이 잘못됨: {path}")
    return data


def fetch_feed(category: str, source: dict, fetched_at: str) -> list[dict]:
    """한 RSS 피드를 파싱해 기사 리스트를 돌려준다. 실패하면 예외를 올린다."""
    name = source.get("매체명", "(이름없음)")
    url = source["url"]

    parsed = feedparser.parse(url, agent=USER_AGENT)

    # bozo: 파싱 중 문제가 있었음을 의미. 단, 엔트리가 있으면 사용 가능한 경우가 많다.
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(parsed.get("bozo_exception", "알 수 없는 파싱 오류"))
    if not parsed.entries:
        raise RuntimeError("기사 엔트리가 0건")

    articles = []
    for entry in parsed.entries:
        articles.append(
            {
                "title": html.unescape(entry.get("title", "")).strip(),
                "link": entry.get("link", "").strip(),
                "published": entry.get("published", entry.get("updated", "")),
                "published_iso": _to_iso(entry),
                "summary": html.unescape(entry.get("summary", "")).strip(),
                "source": name,
                "category": category,
                "fetched_at": fetched_at,
            }
        )
    return articles


def _to_iso(entry) -> str:
    """feedparser가 파싱한 발행시각(UTC struct)을 ISO 문자열로 정규화한다.

    매체마다 published 형식이 제각각이라(RFC822/ISO/공백구분) 원본 문자열 대신
    feedparser가 정규화한 *_parsed 값을 쓴다. 파싱 불가면 빈 문자열.
    """
    pp = entry.get("published_parsed") or entry.get("updated_parsed")
    if not pp:
        return ""
    return datetime.fromtimestamp(calendar.timegm(pp), tz=timezone.utc).isoformat()


def collect(sources: dict) -> dict:
    """모든 출처를 돌며 기사를 모으고, 실패 출처를 함께 기록한다."""
    fetched_at = datetime.now().isoformat(timespec="seconds")
    articles: list[dict] = []
    counts: dict[str, int] = {}
    failed: list[dict] = []

    for category, source_list in sources.items():
        counts[category] = 0
        for source in source_list:
            name = source.get("매체명", "(이름없음)")
            url = source.get("url", "")
            try:
                got = fetch_feed(category, source, fetched_at)
                articles.extend(got)
                counts[category] += len(got)
                print(f"  [OK] {category} / {name}: {len(got)}건")
            except Exception as exc:  # noqa: BLE001 - 한 소스 실패가 전체를 멈추면 안 됨
                failed.append({"category": category, "source": name, "url": url, "error": str(exc)})
                print(f"  [실패] {category} / {name}: {exc}", file=sys.stderr)

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "fetched_at": fetched_at,
        "counts": counts,
        "failed_sources": failed,
        "articles": articles,
    }


def save(result: dict) -> Path:
    """수집 결과를 raw/YYYY-MM-DD.json 으로 저장한다(덮어쓰기)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{result['date']}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return out_path


def main() -> int:
    print(f"출처 설정 읽는 중: {SOURCES_FILE}")
    try:
        sources = load_sources(SOURCES_FILE)
    except Exception as exc:  # noqa: BLE001
        print(f"오류: 출처 설정을 읽을 수 없음 - {exc}", file=sys.stderr)
        return 1

    print("수집 시작...")
    result = collect(sources)

    total = len(result["articles"])
    if total == 0:
        # 모든 소스 실패 → 파일을 만들지 않고 명확히 알린다.
        print("오류: 모든 출처에서 기사를 가져오지 못했습니다. 파일을 생성하지 않습니다.", file=sys.stderr)
        return 1

    out_path = save(result)

    print("\n=== 수집 요약 ===")
    for category, n in result["counts"].items():
        print(f"  {category}: {n}건")
    print(f"  총 {total}건, 실패 출처 {len(result['failed_sources'])}곳")
    print(f"저장됨: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
