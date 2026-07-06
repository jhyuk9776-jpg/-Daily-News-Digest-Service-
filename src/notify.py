"""오늘의 뉴스 요약(News/<date>.md)을 HTML+카톡용 plain 메일로 발송한다.

파싱→렌더→발송을 함수로 분리해 unittest로 검증 가능하게 한다(네트워크/SMTP 미사용).
아침 cron이 다이제스트를 커밋한 뒤 워크플로에서 `python3 src/notify.py`로 실행된다.

실행: python3 src/notify.py   # 오늘(KST) News/<date>.md를 발송
"""
import html as html_lib
import os
import re
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

KST = timezone(timedelta(hours=9))
NEWS_DIR = Path(__file__).resolve().parent.parent / "News"

_SOURCE_RE = re.compile(r"^출처:\s*\[([^\]]+)\]\(([^)]+)\)(.*)$")


def parse_digest(md_text: str) -> dict:
    """다이제스트 마크다운을 구조화한다."""
    title_line = ""
    meta = ""
    categories: list[dict] = []
    current_cat = None
    current_article = None
    for raw in md_text.splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            title_line = line[2:].strip()
        elif line.startswith("> "):
            meta = line[2:].strip()
        elif line.startswith("## "):
            current_cat = {"name": line[3:].strip(), "articles": []}
            categories.append(current_cat)
            current_article = None
        elif line.startswith("### "):
            current_article = {"title": line[4:].strip(), "bullets": [], "source": None}
            if current_cat is not None:
                current_cat["articles"].append(current_article)
        elif line.startswith("- ") and current_article is not None:
            body = line[2:].strip()
            m = _SOURCE_RE.match(body)
            if m:
                current_article["source"] = {
                    "label": m.group(1),
                    "url": m.group(2),
                    "extra": m.group(3).strip(),
                }
            else:
                current_article["bullets"].append(body)
    total_count = sum(len(c["articles"]) for c in categories)
    return {
        "title_line": title_line,
        "meta": meta,
        "categories": categories,
        "total_count": total_count,
    }
