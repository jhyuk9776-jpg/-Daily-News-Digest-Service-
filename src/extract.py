"""Day 4: 기사 내용 확보(본문 추출 + 클러스터 폴백 체인).

요약에 쓸 텍스트 후보를 우선순위 순으로 하나씩 내보낸다(제너레이터).
각 매체마다:
  - RSS 요약이 충분하면 먼저 내보낸다(HTTP 없이 저렴).
  - 이어서 본문 추출 결과를 내보낸다(짧은 RSS 보강).
후보 순서: 대표 매체(RSS→본문) → 같은 사건(클러스터)의 다음 우선순위 매체(본문).

소비자(summarize)는 요약 불릿이 나오는 첫 후보에서 멈춘다. 앞 후보에서 성공하면
제너레이터가 더 진행되지 않으므로 불필요한 본문 추출/HTTP가 발생하지 않는다.
본문 추출은 최종 선별된 8건에만 적용되므로 호출량이 적다.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

MIN_SUMMARY = 40   # 이 길이 이상이면 RSS 요약을 그대로 사용(본문 추출 생략)
MIN_BODY = 80      # 본문 추출 결과가 이 길이 미만이면 실패로 간주
MAX_CHARS = 2000   # 요약 입력으로 넘길 본문 최대 길이(비용 제한)
TIMEOUT = 10

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_DATE_RE = re.compile(r"20\d{2}[.\-/]\s?\d{1,2}[.\-/]\s?\d{1,2}")
_TITLE_STOPWORDS = {"오늘", "관련", "기자", "뉴스", "속보", "단독"}


def _title_keywords(title: str) -> list[str]:
    toks = re.findall(r"[가-힣A-Za-z0-9]{2,}", title)
    return [t for t in toks if t not in _TITLE_STOPWORDS]


def looks_like_body(text: str, title: str = "") -> bool:
    """추출 텍스트가 진짜 기사 본문인지 검증한다(추천위젯·제목불일치 기각)."""
    if len(text) < MIN_BODY:
        return False
    if len(_DATE_RE.findall(text)) >= 3:
        return False
    keywords = _title_keywords(title)
    if keywords and not any(k in text for k in keywords):
        return False
    return True


# 도메인 → 진짜 본문 컨테이너 CSS 선택자 후보(있으면 우선, 없으면 휴리스틱 폴백).
# 선택자가 매치되면 컨테이너 전체 텍스트를 쓴다(본문이 <p> 없이 div에 직접 들어가는 매체 대응).
SITE_SELECTORS: dict[str, list[str]] = {
    "hankyung.com": ["#articletxt", ".article-body"],
    # 나머지 도메인은 Task 6에서 확인해 채운다(폴백+가드가 안전망).
}


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _parse_body(html: str, url: str, title: str = "") -> str | None:
    """HTML에서 본문을 추출한다(도메인 선택자 우선 → 휴리스틱 폴백 → 가드). 실패 시 None."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    container = None
    for sel in SITE_SELECTORS.get(_domain(url), []):
        container = soup.select_one(sel)
        if container:
            break

    if container is not None:
        text = container.get_text(" ", strip=True)
    else:
        # 기사 본문은 보통 <article> 또는 다수의 <p>에 들어 있다.
        article = soup.find("article")
        paragraphs = (article or soup).find_all("p")
        text = " ".join(p.get_text(" ", strip=True) for p in paragraphs)

    text = " ".join(text.split())[:MAX_CHARS]  # 공백 정리
    if not looks_like_body(text, title):
        return None
    return text


def extract_body(url: str, title: str = "") -> str | None:
    """원문 링크에서 본문 텍스트를 추출한다(도메인 선택자+가드). 실패하면 None."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    return _parse_body(resp.text, url, title)


def candidate_sources(item: dict):
    """요약 후보 매체를 우선순위 순으로 (매체명, 링크, RSS요약)으로 내보낸다.

    대표 매체(1순위)가 먼저, 이어서 같은 사건의 관련 매체(우선순위 순)가 온다.
    """
    yield (item["source"], item["link"], item.get("summary", ""))
    for rl in item.get("related_links", []):
        yield (rl["source"], rl["link"], "")


def iter_contents(item: dict):
    """선별 항목에서 요약에 쓸 텍스트 후보를 우선순위 순으로 하나씩 내보낸다.

    각 후보: {"text", "content_source", "method", "link"}.
    method: "rss"(요약 그대로) | "body"(본문 추출).
    매체마다 충분한 RSS 요약을 먼저, 이어서 본문 추출 결과를 내보낸다.
    제너레이터라 소비자가 필요할 때만 다음 후보(및 본문 추출)를 계산한다.
    """
    for source, link, summary in candidate_sources(item):
        if summary and len(summary) >= MIN_SUMMARY:
            yield {"text": summary, "content_source": source, "method": "rss", "link": link}
        body = extract_body(link)
        if body:
            yield {"text": body, "content_source": source, "method": "body", "link": link}
