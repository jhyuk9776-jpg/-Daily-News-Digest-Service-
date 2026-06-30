"""Day 4: 기사 내용 확보(본문 추출 + 클러스터 폴백 체인).

요약에 쓸 텍스트를 정한다.
  - 대표 매체의 RSS 요약이 충분하면 그대로 사용(본문 추출 안 함)
  - 비었/짧으면 대표 매체 본문 추출 시도
  - 실패하면 같은 사건(클러스터)의 다음 우선순위 매체 본문으로 순차 재시도
  - 모든 매체에서 실패하면 None (요약 제외 안내 대상)

본문 추출은 최종 선별된 8건에만 적용되므로 호출량이 적다.
"""

from __future__ import annotations

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


def extract_body(url: str) -> str | None:
    """원문 링크에서 본문 텍스트를 추출한다. 실패하면 None."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # 기사 본문은 보통 <article> 또는 다수의 <p>에 들어 있다.
    article = soup.find("article")
    paragraphs = (article or soup).find_all("p")
    text = " ".join(p.get_text(" ", strip=True) for p in paragraphs)
    text = " ".join(text.split())  # 공백 정리

    if len(text) < MIN_BODY:
        return None
    return text[:MAX_CHARS]


def get_content(item: dict) -> dict | None:
    """선별 항목에서 요약에 쓸 텍스트를 확보한다.

    반환: {"text", "content_source", "method"} 또는 None(모든 매체 실패).
    method: "rss"(요약 그대로) | "body"(본문 추출).
    """
    # 후보: 대표 매체(요약 보유) → 클러스터 내 다른 매체(본문 추출)
    candidates = [(item["source"], item["link"], item.get("summary", ""))]
    for rl in item.get("related_links", []):
        candidates.append((rl["source"], rl["link"], ""))

    for source, link, summary in candidates:
        if summary and len(summary) >= MIN_SUMMARY:
            return {"text": summary, "content_source": source, "method": "rss"}
        body = extract_body(link)
        if body:
            return {"text": body, "content_source": source, "method": "body"}

    return None
