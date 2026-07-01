"""Day 4: AI 요약 + 마크다운 생성 (파이프라인 마지막 단계).

selected/YYYY-MM-DD.json(선별 결과)을 입력으로 받아
  1) 내용 확보: extract.get_content (빈 요약만 본문 추출 + 클러스터 폴백)
  2) URL 캐시 확인 (같은 기사 반복 요약 방지)
  3) Claude Haiku 4.5로 사실 중심 1~3문장 요약 (기사별 개별 호출)
     - Replicate 경유 호출(모델: anthropic/claude-4.5-haiku). Anthropic 콘솔 결제가
       막혀 Replicate 공식 채널로 같은 모델을 사용한다(기획/04-decision-log 1.2 참고).
  4) 마크다운 조립 → News/YYYY-MM-DD.md
출처는 사실 단위로 1:1 부착한다("출처 없는 사실은 싣지 않는다").

요약 규칙은 AI_CONTEXT.md §6 기반. 결정은 기획/04-decision-log.md "1.2" 참고.

실행:
    python3 src/summarize.py            # selected/<오늘>.json 사용
    python3 src/summarize.py --dry-run  # API 호출 없이 흐름만 검증
    python3 src/summarize.py 2026-06-30 # 특정 날짜
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

from extract import iter_contents

ROOT = Path(__file__).resolve().parent.parent
SELECTED_DIR = ROOT / "selected"
NEWS_DIR = ROOT / "News"
CACHE_FILE = ROOT / "cache" / "summaries.json"

KST = timezone(timedelta(hours=9))
MODEL = "anthropic/claude-4.5-haiku"  # Replicate 경유 Claude Haiku 4.5
MAX_TOKENS = 1024   # Replicate Claude 모델 최소값
THROTTLE_WAIT = 12  # 429(분당 제한) 시 대기 초
MAX_RETRY = 5

# 요약 생성 실패(api_failed)가 전체 대비 이 비율 이상이면 조용한 품질 붕괴로 보고
# 비정상 종료한다. 링크-only 폴백은 개별 기사의 최후 수단이지, 401 인증 실패처럼
# 전량이 무너진 상황까지 "성공"으로 넘기라는 뜻이 아니다(무인 실행 시 CI 빨간불).
FAIL_RATIO = 0.5

# 사실 중심 요약 규칙 (AI_CONTEXT.md §6)
SYSTEM_PROMPT = """당신은 사실 중심 뉴스 다이제스트의 편집자다. 주어진 기사에서 사실만 뽑아 짧게 정리한다.

규칙:
- 사건, 수치, 날짜, 발언 주체를 우선한다.
- 평가어와 감정적 표현을 쓰지 않는다.
- 원문에 없는 배경 지식이나 추측을 덧붙이지 않는다.
- 전망·추측은 원문에 명시된 경우에만 "누가 말했다" 형태로 적는다.
- "논란이 커지고 있다", "충격을 주고 있다", "큰 파장이 예상된다", "업계가 주목하고 있다" 같은 표현을 쓰지 않는다.
- 확인되지 않은 내용은 적지 않는다.

출력 형식(반드시 지킨다):
- 오직 "- "로 시작하는 불릿 줄만 출력한다. 사실 1~3개를 각각 한 줄로 적는다.
- 인사말, 설명, 사과, 되묻는 질문, 본문 요청, 메타 발언을 절대 하지 않는다.
- 본문이 부족해도 확인 가능한 사실만 불릿로 낸다. 낼 사실이 하나도 없으면 아무것도 출력하지 않는다."""


def load_selected(date: str) -> dict:
    path = SELECTED_DIR / f"{date}.json"
    if not path.exists():
        raise FileNotFoundError(f"선별 결과가 없음: {path} (먼저 curate.py 실행)")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_cache() -> dict:
    if CACHE_FILE.exists():
        with CACHE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_FILE.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def parse_bullets(text: str) -> list[str]:
    """모델 출력에서 불릿 문장만 추출한다."""
    bullets = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(("-", "•", "*")):
            cleaned = line.lstrip("-•* ").strip()
            if cleaned:
                bullets.append(cleaned)
    return bullets[:3]


def summarize_one(title: str, source: str, text: str) -> list[str]:
    """기사 1건을 사실 불릿으로 요약한다(Replicate 경유 개별 호출).

    Replicate 모델 출력은 토큰 조각 문자열의 이터레이터라 이어붙여 사용한다.
    """
    import time

    import replicate

    user = f"제목: {title}\n출처: {source}\n내용:\n{text}"
    inputs = {"prompt": user, "system_prompt": SYSTEM_PROMPT, "max_tokens": MAX_TOKENS}

    for attempt in range(MAX_RETRY):
        try:
            output = replicate.run(MODEL, input=inputs)
            out = "".join(str(chunk) for chunk in output)
            return parse_bullets(out)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            # 429: 잔액 $5 미만이면 분당 6건 제한. 잠시 대기 후 재시도.
            if ("429" in msg or "throttled" in msg.lower()) and attempt < MAX_RETRY - 1:
                time.sleep(THROTTLE_WAIT)
                continue
            raise
    raise RuntimeError("요청 제한(429) 재시도 초과")


def summarize_item(item: dict, cache: dict, dry_run: bool):
    """기사 1건을 폴백 체인으로 요약한다.

    우선순위 순 후보(대표 매체 RSS/본문 → 다음 순위 매체 본문)를 돌며,
    요약 불릿이 나오는 첫 후보를 쓴다. 앞 후보에서 성공하면 뒤 후보는 시도하지 않는다.

    반환: (bullets, content_source, status, cached)
      status: "ok"          — 어떤 후보에서 불릿을 얻음
              "api_failed"   — 후보 텍스트는 있었으나 모든 후보에서 불릿 0개
              "extract_failed" — 후보 텍스트를 하나도 못 만듦
    """
    had_content = False
    for content in iter_contents(item):
        had_content = True
        link = content["link"]
        source = content["content_source"]

        if link in cache:
            return cache[link], source, "ok", True
        if dry_run:
            return ["(dry-run: 요약 생략)"], source, "ok", False

        try:
            bullets = summarize_one(item["title"], source, content["text"])
        except Exception as exc:  # noqa: BLE001 - 한 후보 실패가 전체를 멈추면 안 됨
            print(f"    [요약오류] {source} / {item['title'][:20]}: {exc}", file=sys.stderr)
            continue

        if bullets:
            cache[link] = bullets
            return bullets, source, "ok", False
        # 불릿 0개 → 다음 우선순위 후보로 폴백

    if had_content:
        return [], None, "api_failed", False
    return [], None, "extract_failed", False


def render_item(item: dict, bullets: list[str], status: str) -> str:
    """선별 항목 1건을 마크다운으로 만든다."""
    lines = [f"### {item['title']}"]
    if status == "ok":
        lines += [f"- {b}" for b in bullets]
    elif status == "extract_failed":
        lines.append("- (본문 추출 실패로 요약 제외)")
    elif status == "api_failed":
        lines.append("- (요약 생성 실패 — 원문 링크만 제공)")

    src = f"- 출처: [{item['source']}]({item['link']})"
    related = item.get("related_links", [])
    if related:
        src += f" 외 관련 {len(related)}건"
    lines.append(src)
    return "\n".join(lines)


def build_markdown(selected: dict, results: dict, counters: dict) -> str:
    date = selected["date"]
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    parts = [
        f"# 데일리 뉴스 다이제스트 - {date}",
        "",
        f"> 생성: {now} · 요약 실패 {counters['api_failed']}건 · 추출 실패 "
        f"{counters['extract_failed']}건",
    ]
    for category, items in selected["categories"].items():
        parts += ["", f"## {category}"]
        if not items:
            parts += ["", "오늘 수집된 주요 기사가 없습니다."]
            continue
        for item in items:
            bullets, status = results[item["link"]]
            parts += ["", render_item(item, bullets, status)]
    parts.append("")
    return "\n".join(parts)


def run(date: str, dry_run: bool) -> int:
    try:
        selected = load_selected(date)
    except FileNotFoundError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    if not dry_run:
        import os
        load_dotenv(ROOT / ".env")
        if not os.environ.get("REPLICATE_API_TOKEN"):
            print("오류: REPLICATE_API_TOKEN이 없습니다. .env 파일을 확인하세요.",
                  file=sys.stderr)
            return 1

    cache = load_cache()
    results: dict[str, tuple[list[str], str]] = {}
    counters = {"ok": 0, "api_failed": 0, "extract_failed": 0, "cached": 0}

    for category, items in selected["categories"].items():
        for item in items:
            bullets, source, status, cached = summarize_item(item, cache, dry_run)
            results[item["link"]] = (bullets, status)

            if status == "ok":
                counters["ok"] += 1
                if cached:
                    counters["cached"] += 1
                    print(f"  [캐시] {category} / {item['title'][:30]}")
                else:
                    print(f"  [요약] {category} / {item['title'][:30]} ({source})")
            elif status == "extract_failed":
                counters["extract_failed"] += 1
                print(f"  [추출실패] {category} / {item['title'][:30]}", file=sys.stderr)
            else:  # api_failed
                counters["api_failed"] += 1
                print(f"  [요약실패] {category} / {item['title'][:30]} "
                      f"(모든 후보 불릿 0)", file=sys.stderr)

    if not dry_run:
        save_cache(cache)

    markdown = build_markdown(selected, results, counters)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = NEWS_DIR / f"{date}.md"
    out_path.write_text(markdown, encoding="utf-8")

    print(f"\n=== 완료 ({date}) ===")
    print(f"  요약 {counters['ok']}건(캐시 {counters['cached']}) · "
          f"요약실패 {counters['api_failed']} · 추출실패 {counters['extract_failed']}")
    print(f"저장됨: {out_path}")

    # 요약 생성 실패가 과반이면 무인 실행에서 조용히 넘기지 않고 비정상 종료한다.
    # (파일은 위에서 이미 저장해 아티팩트로 확인 가능하되, run.sh의 set -e가
    #  자동커밋 단계를 막아 부실한 다이제스트가 main에 올라가는 것을 차단한다.)
    total = counters["ok"] + counters["api_failed"] + counters["extract_failed"]
    if not dry_run and total and counters["api_failed"] / total >= FAIL_RATIO:
        print(f"오류: 요약 생성 실패가 과반입니다 "
              f"({counters['api_failed']}/{total}, 기준 {FAIL_RATIO:.0%}). "
              f"토큰·API 상태를 확인하세요.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:]]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    date = args[0] if args else datetime.now(KST).strftime("%Y-%m-%d")
    return run(date, dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
