"""오늘의 뉴스 요약(News/<date>.md)을 HTML 메일로 발송한다(plain은 MIME 폴백).

파싱→렌더→발송을 함수로 분리해 unittest로 검증 가능하게 한다(네트워크/SMTP 미사용).
아침 cron이 다이제스트를 커밋한 뒤 워크플로에서 `python3 src/notify.py`로 실행된다.

실행: python3 src/notify.py   # 오늘(KST) News/<date>.md를 발송
"""
from __future__ import annotations

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


def _render_text(digest: dict) -> str:
    lines = [digest["title_line"], ""]
    for cat in digest["categories"]:
        lines.append(f"──────── {cat['name']} ────────")
        for art in cat["articles"]:
            lines.append(f"▪ {art['title']}")
            for b in art["bullets"]:
                lines.append(f"  · {b}")
            src = art["source"]
            if src:
                # 카톡용(plain)은 출처명만 — URL은 복붙 시 지저분해 뺀다(링크는 HTML에만).
                extra = f" {src['extra']}" if src["extra"] else ""
                lines.append(f"  출처: {src['label']}{extra}")
            lines.append("")
    if digest["meta"]:
        lines.append(f"— {digest['meta']}")
    return "\n".join(lines).strip() + "\n"


def _render_html(digest: dict) -> str:
    esc = html_lib.escape
    parts = [f"<h1>{esc(digest['title_line'])}</h1>"]
    for cat in digest["categories"]:
        parts.append(f"<h2>{esc(cat['name'])}</h2>")
        for art in cat["articles"]:
            parts.append(f"<h3>{esc(art['title'])}</h3>")
            if art["bullets"]:
                parts.append("<ul>")
                parts += [f"<li>{esc(b)}</li>" for b in art["bullets"]]
                parts.append("</ul>")
            src = art["source"]
            if src:
                extra = f" {esc(src['extra'])}" if src["extra"] else ""
                parts.append(
                    f'<p>출처: <a href="{esc(src["url"])}">{esc(src["label"])}</a>{extra}</p>'
                )
    if digest["meta"]:
        parts.append(
            f'<p style="color:#888;font-size:12px">{esc(digest["meta"])}</p>'
        )
    return "<html><body>" + "\n".join(parts) + "</body></html>"


def render_email(digest: dict) -> tuple[str, str, str]:
    subject = f"📰 {digest['title_line']} ({digest['total_count']}건)"
    text_body = _render_text(digest)
    html_body = _render_html(digest)
    return subject, html_body, text_body


def send_email(
    subject: str,
    html_body: str,
    text_body: str,
    address: str,
    app_password: str,
    to: str | None = None,
) -> None:
    to = to or address
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = address
    msg["To"] = to
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(address, app_password)
        server.send_message(msg)


def main() -> int:
    date = datetime.now(KST).strftime("%Y-%m-%d")
    path = NEWS_DIR / f"{date}.md"
    if not path.exists():
        print(f"발송 스킵: 오늘 다이제스트 없음 ({path})")
        return 0
    address = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not address or not app_password:
        print("발송 실패: GMAIL_ADDRESS/GMAIL_APP_PASSWORD 미설정", file=sys.stderr)
        return 1
    to = os.environ.get("NOTIFY_TO") or address
    digest = parse_digest(path.read_text(encoding="utf-8"))
    subject, html_body, text_body = render_email(digest)
    try:
        send_email(subject, html_body, text_body, address, app_password, to)
    except Exception as exc:  # noqa: BLE001 - 실패는 빨간불로 노출, 스택 대신 원인 요약
        print(f"발송 실패: {exc}", file=sys.stderr)
        return 1
    print(f"발송 완료: {to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
