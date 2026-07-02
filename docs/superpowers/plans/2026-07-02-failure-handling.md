# 실패 처리(제외 + 실패 로그 + 알림) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사실을 못 뽑은 기사를 다이제스트에서 제외하고, 실패를 원인별로 `failures/failures-YYYY-MM-DD.json`에 누적 기록하며, 실패 발생 시 CLI로 알린다.

**Architecture:** `summarize_item`이 실패 원인을 세분(api_failed/call_error/extract_failed)해 detail과 함께 반환한다. `summarize.run()`은 성공만 다이제스트에 렌더하고 실패는 목록으로 모아 신규 모듈 `src/failure_log.py`로 저장한다. daily 자동커밋이 `failures/`를 포함해 누적한다.

**Tech Stack:** Python 3.9 표준 라이브러리 + 표준 `unittest`(네트워크/API는 mock).

## Global Constraints

- Python 3.9 호환. 3.10+ 문법 금지.
- `summarize_item` 반환은 **5-튜플** `(bullets, source, status, cached, detail)`로 확장. 기존 4-튜플 언패킹(테스트·run)을 모두 갱신한다.
- FAIL_RATIO 가드는 `api_failed + call_error`를 실패로 센다(401 대량 인증실패가 call_error로 분류돼도 가드가 유지되도록). extract_failed는 가드에서 제외(기존 동작 유지).
- 실패 0건이면 `failures-*.json`을 만들지 않는다.
- 격리: curate/objectivity 무변경. daily.yml은 `git add` 한 줄만 확장.
- 테스트 실행: `python3 -m unittest discover -s tests`.
- 커밋 트레일러: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## File Structure

- Create: `src/failure_log.py` — 실패 로그 파일 I/O(단일 책임)
- Create: `tests/test_failure_log.py` — 실패 로그 테스트
- Modify: `src/summarize.py` — summarize_item 원인 세분, run 제외·수집·저장·알림·가드, build_markdown/render_item
- Modify: `tests/test_fallback.py` — 5-튜플 언패킹 갱신 + call_error/제외 테스트 추가
- Modify: `.github/workflows/daily.yml` — 자동커밋에 `failures/` 포함
- Modify: `.gitignore` — `failures/` 추적 예외 주석
- 런타임 생성: `failures/failures-YYYY-MM-DD.json`

---

## Task 1: 실패 로그 모듈 `failure_log.py`

**Files:**
- Create: `src/failure_log.py`
- Test: `tests/test_failure_log.py`

**Interfaces:**
- Produces: `FAILURES_DIR` (Path), `save_failure_log(date, total_articles, failures)` →
  실패 0건이면 `None`, 아니면 `failures/failures-<date>.json` 기록 후 `Path` 반환.
  `failures`: `list[dict]` 각 `{category, source, title, link, reason, detail}`.

- [ ] **Step 1: Write the failing test**

`tests/test_failure_log.py`:
```python
"""실패 로그 저장 테스트 (표준 unittest, 네트워크/API 미사용)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import failure_log  # noqa: E402


class SaveFailureLogTest(unittest.TestCase):
    def _failures(self):
        return [{"category": "경제", "source": "한국경제", "title": "칼럼",
                 "link": "L1", "reason": "api_failed", "detail": "모든 후보 불릿 0"}]

    def test_writes_file_with_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(failure_log, "FAILURES_DIR", Path(tmp)):
                path = failure_log.save_failure_log("2026-07-01", 16, self._failures())
                data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(data["date"], "2026-07-01")
        self.assertEqual(data["total_articles"], 16)
        self.assertEqual(data["failed_count"], 1)
        self.assertEqual(data["failures"][0]["reason"], "api_failed")
        self.assertIn("generated_at", data)

    def test_no_failures_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(failure_log, "FAILURES_DIR", Path(tmp)):
                result = failure_log.save_failure_log("2026-07-01", 16, [])
                files = list(Path(tmp).glob("*.json"))
        self.assertIsNone(result)
        self.assertEqual(files, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_failure_log -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'failure_log'`

- [ ] **Step 3: Write minimal implementation**

`src/failure_log.py`:
```python
"""파이프라인 실패 로그 축적 (요약 실패·본문추출 실패·호출 예외).

실패·에러 데이터는 추출기 개선·엣지케이스 사전의 연료다. 실패 0건이면 파일을
만들지 않는다. failures/는 git 추적해 커밋으로 누적한다(scores/ 선례).

설계: docs/superpowers/specs/2026-07-02-failure-handling-design.md
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURES_DIR = ROOT / "failures"
KST = timezone(timedelta(hours=9))


def save_failure_log(date: str, total_articles: int, failures: list):
    """실패 목록을 failures/failures-<date>.json에 기록한다.

    실패 0건이면 아무것도 만들지 않고 None을 반환한다.
    """
    if not failures:
        return None
    FAILURES_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": date,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "total_articles": total_articles,
        "failed_count": len(failures),
        "failures": failures,
    }
    path = FAILURES_DIR / f"failures-{date}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_failure_log -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/failure_log.py tests/test_failure_log.py
git commit -m "feat: 실패 로그 모듈 failure_log (실패 0건이면 미생성)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: summarize_item 실패 원인 세분(call_error) + detail

**Files:**
- Modify: `src/summarize.py` (`summarize_item`)
- Test: `tests/test_fallback.py`

**Interfaces:**
- Produces: `summarize_item(item, cache, dry_run)` → **5-튜플**
  `(bullets, source, status, cached, detail)`.
  status ∈ {ok, api_failed, call_error, extract_failed}.
  detail: 실패 사유 문자열(성공 시 None). call_error면 마지막 예외 메시지.

- [ ] **Step 1: Update existing tests to 5-tuple + add cause tests**

`tests/test_fallback.py` — `SummarizeItemTest`의 모든 언패킹을 5개로 바꾸고 케이스 추가.
기존 각 줄 `bullets, source, status, cached = summarize.summarize_item(...)` 을
`bullets, source, status, cached, detail = summarize.summarize_item(...)` 로 바꾼다(6곳).
그리고 클래스에 아래 두 테스트를 추가:
```python
    @patch("summarize.summarize_one")
    @patch("summarize.iter_contents")
    def test_all_exceptions_returns_call_error(self, m_iter, m_sum):
        m_iter.return_value = iter([
            {"text": "a", "content_source": "매일경제", "method": "rss", "link": "L1"},
            {"text": "b", "content_source": "연합", "method": "body", "link": "L2"},
        ])
        m_sum.side_effect = [RuntimeError("401 Unauthorized"), RuntimeError("500")]
        bullets, source, status, cached, detail = summarize.summarize_item(_item(), {}, False)
        self.assertEqual(status, "call_error")
        self.assertIn("500", detail)

    @patch("summarize.summarize_one")
    @patch("summarize.iter_contents")
    def test_empty_bullets_no_exception_is_api_failed(self, m_iter, m_sum):
        m_iter.return_value = iter([
            {"text": "a", "content_source": "매일경제", "method": "rss", "link": "L1"},
        ])
        m_sum.side_effect = [[]]
        bullets, source, status, cached, detail = summarize.summarize_item(_item(), {}, False)
        self.assertEqual(status, "api_failed")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_fallback.SummarizeItemTest -v`
Expected: FAIL — 기존 테스트는 `ValueError: not enough values to unpack (expected 5, got 4)`,
신규 test_all_exceptions_returns_call_error는 `AssertionError: 'api_failed' != 'call_error'`.

- [ ] **Step 3: Write minimal implementation**

`src/summarize.py` — `summarize_item` 전체를 아래로 교체(반환 5-튜플, last_error 추적):
```python
def summarize_item(item: dict, cache: dict, dry_run: bool):
    """기사 1건을 폴백 체인으로 요약한다.

    반환: (bullets, content_source, status, cached, detail)
      status: "ok"            — 어떤 후보에서 불릿을 얻음
              "call_error"    — 후보 처리 중 예외가 났고 끝까지 불릿 0 (detail=마지막 예외)
              "api_failed"    — 예외 없이 모든 후보 불릿 0 (사실 못 뽑음)
              "extract_failed" — 후보 텍스트를 하나도 못 만듦
    """
    had_content = False
    last_error = None
    for content in iter_contents(item):
        had_content = True
        link = content["link"]
        source = content["content_source"]

        if link in cache:
            return cache[link], source, "ok", True, None
        if dry_run:
            return ["(dry-run: 요약 생략)"], source, "ok", False, None

        try:
            bullets = summarize_one(item["title"], source, content["text"])
        except Exception as exc:  # noqa: BLE001 - 한 후보 실패가 전체를 멈추면 안 됨
            last_error = str(exc)
            print(f"    [요약오류] {source} / {item['title'][:20]}: {exc}", file=sys.stderr)
            continue

        if bullets:
            cache[link] = bullets
            return bullets, source, "ok", False, None
        # 불릿 0개 → 다음 우선순위 후보로 폴백

    if not had_content:
        return [], None, "extract_failed", False, None
    if last_error is not None:
        return [], None, "call_error", False, last_error
    return [], None, "api_failed", False, "모든 후보 불릿 0"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_fallback.SummarizeItemTest -v`
Expected: PASS (기존 6 + 신규 2 = 8 tests). RunExitCodeTest는 아직 4-튜플이라 여기선 실행하지 않는다(Task 3에서 갱신).

- [ ] **Step 5: Commit**

```bash
git add src/summarize.py tests/test_fallback.py
git commit -m "feat: summarize_item 실패 원인 세분(call_error) + detail 반환

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: run() 실패 제외·수집·저장·알림·가드 + 렌더 정리

**Files:**
- Modify: `src/summarize.py` (`run`, `build_markdown`, `render_item`)
- Test: `tests/test_fallback.py` (`RunExitCodeTest` 갱신 + 제외/전원실패 테스트)

**Interfaces:**
- Consumes: `summarize_item`(Task 2, 5-튜플), `failure_log.save_failure_log`(Task 1)
- Produces: `run(date, dry_run)` — 성공만 렌더, 실패는 로그 저장 + 알림.
  `build_markdown(selected, results, counters)` — results에 있는(성공) 항목만 렌더.

- [ ] **Step 1: Update RunExitCodeTest + add exclusion tests**

`tests/test_fallback.py` — `RunExitCodeTest._run_with_statuses`의 side 튜플을 5개로:
```python
        side = [(["사실"] if s == "ok" else [], "매일경제", s, False, None)
                for s in statuses]
```
그리고 `patch.object(summarize, "NEWS_DIR", Path(tmp))` 옆에
`patch("summarize.save_failure_log")`를 추가(실제 파일 안 쓰게):
```python
            with patch.dict(os.environ, {"REPLICATE_API_TOKEN": "x"}), \
                 patch("summarize.load_selected", return_value=selected), \
                 patch("summarize.load_cache", return_value={}), \
                 patch("summarize.save_cache"), \
                 patch("summarize.save_failure_log"), \
                 patch("summarize.summarize_item", side_effect=side), \
                 patch.object(summarize, "NEWS_DIR", Path(tmp)):
                return summarize.run("2026-07-01", dry_run=False)
```
같은 클래스에 call_error 가드 테스트 추가:
```python
    def test_majority_call_error_returns_nonzero(self):
        # 401 대량 인증실패는 call_error로 분류되어도 가드가 잡아야 한다.
        self.assertEqual(self._run_with_statuses(["call_error"] * 8), 1)
```

신규 클래스 `BuildMarkdownExclusionTest`를 파일에 추가:
```python
class BuildMarkdownExclusionTest(unittest.TestCase):
    def _item(self, link):
        return {"title": f"제목{link}", "source": "매일경제", "link": link,
                "related_links": []}

    def test_failed_items_excluded_from_body(self):
        selected = {"date": "2026-07-01", "categories": {"경제": [
            self._item("L1"), self._item("L2")]}}
        results = {"L1": (["사실"], "ok")}  # L2는 실패라 results에 없음
        counters = {"ok": 1, "api_failed": 1, "call_error": 0, "extract_failed": 0, "cached": 0}
        md = summarize.build_markdown(selected, results, counters)
        self.assertIn("제목L1", md)
        self.assertNotIn("제목L2", md)

    def test_all_failed_category_shows_empty_message(self):
        selected = {"date": "2026-07-01", "categories": {"경제": [self._item("L1")]}}
        results = {}  # 전원 실패
        counters = {"ok": 0, "api_failed": 1, "call_error": 0, "extract_failed": 0, "cached": 0}
        md = summarize.build_markdown(selected, results, counters)
        self.assertIn("오늘 수집된 주요 기사가 없습니다", md)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_fallback.RunExitCodeTest tests.test_fallback.BuildMarkdownExclusionTest -v`
Expected: FAIL — RunExitCodeTest는 `run`이 아직 5-튜플/ save_failure_log 미사용이라 언패킹 오류,
BuildMarkdownExclusionTest는 `build_markdown`이 실패 항목에서 `results[link]` KeyError.

- [ ] **Step 3: Write minimal implementation**

`src/summarize.py` — `render_item`을 성공 전용으로 단순화(실패 분기 제거):
```python
def render_item(item: dict, bullets: list) -> str:
    """선별 항목 1건(요약 성공)을 마크다운으로 만든다."""
    lines = [f"### {item['title']}"]
    lines += [f"- {b}" for b in bullets]
    src = f"- 출처: [{item['source']}]({item['link']})"
    related = item.get("related_links", [])
    if related:
        src += f" 외 관련 {len(related)}건"
    lines.append(src)
    return "\n".join(lines)
```

`src/summarize.py` — `build_markdown`에서 성공 항목만 렌더:
```python
def build_markdown(selected: dict, results: dict, counters: dict) -> str:
    date = selected["date"]
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    parts = [
        f"# 데일리 뉴스 다이제스트 - {date}",
        "",
        f"> 생성: {now} · 요약실패 {counters['api_failed']}건 · 호출오류 "
        f"{counters['call_error']}건 · 추출실패 {counters['extract_failed']}건",
    ]
    for category, items in selected["categories"].items():
        parts += ["", f"## {category}"]
        ok_items = [it for it in items if it["link"] in results]
        if not ok_items:
            parts += ["", "오늘 수집된 주요 기사가 없습니다."]
            continue
        for item in ok_items:
            bullets, status = results[item["link"]]
            parts += ["", render_item(item, bullets)]
    parts.append("")
    return "\n".join(parts)
```

`src/summarize.py` 상단 import에 추가(기존 `from extract import iter_contents` 아래):
```python
from failure_log import save_failure_log
```

`src/summarize.py` — `run()`의 카운터·루프·후처리를 아래로 교체.
현재 `counters = {...}` 부터 `return 0` 직전까지를 대체한다:
```python
    cache = load_cache()
    results = {}
    counters = {"ok": 0, "api_failed": 0, "call_error": 0,
                "extract_failed": 0, "cached": 0}
    failures = []

    for category, items in selected["categories"].items():
        for item in items:
            bullets, source, status, cached, detail = summarize_item(item, cache, dry_run)

            if status == "ok":
                results[item["link"]] = (bullets, status)
                counters["ok"] += 1
                if cached:
                    counters["cached"] += 1
                    print(f"  [캐시] {category} / {item['title'][:30]}")
                else:
                    print(f"  [요약] {category} / {item['title'][:30]} ({source})")
            else:
                counters[status] += 1
                failures.append({
                    "category": category, "source": item["source"],
                    "title": item["title"], "link": item["link"],
                    "reason": status, "detail": detail or "",
                })
                label = {"api_failed": "요약실패", "call_error": "호출오류",
                         "extract_failed": "추출실패"}[status]
                print(f"  [{label}] {category} / {item['title'][:30]}", file=sys.stderr)

    if not dry_run:
        save_cache(cache)

    markdown = build_markdown(selected, results, counters)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = NEWS_DIR / f"{date}.md"
    out_path.write_text(markdown, encoding="utf-8")

    total = counters["ok"] + counters["api_failed"] + counters["call_error"] \
        + counters["extract_failed"]
    log_path = save_failure_log(date, total, failures)

    print(f"\n=== 완료 ({date}) ===")
    print(f"  요약 {counters['ok']}건(캐시 {counters['cached']}) · "
          f"요약실패 {counters['api_failed']} · 호출오류 {counters['call_error']} · "
          f"추출실패 {counters['extract_failed']}")
    print(f"저장됨: {out_path}")

    # 실패 알림: 조용히 넘기지 않는다.
    if failures:
        print(f"\n⚠ 실패 {len(failures)}건 — 기록: {log_path}", file=sys.stderr)
        for f in failures:
            print(f"    - [{f['reason']}] {f['category']} / {f['title'][:30]} "
                  f"({f['source']})", file=sys.stderr)

    # 요약을 못 낸 실패(api_failed+call_error)가 과반이면 조용한 붕괴로 보고 비정상 종료.
    guard_failures = counters["api_failed"] + counters["call_error"]
    if not dry_run and total and guard_failures / total >= FAIL_RATIO:
        print(f"오류: 요약 실패가 과반입니다 "
              f"({guard_failures}/{total}, 기준 {FAIL_RATIO:.0%}). "
              f"토큰·API 상태를 확인하세요.", file=sys.stderr)
        return 1
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_fallback -v`
Expected: PASS (SummarizeItemTest 8 + RunExitCodeTest 5 + BuildMarkdownExclusionTest 2).

- [ ] **Step 5: Run full suite (회귀 확인)**

Run: `python3 -m unittest discover -s tests`
Expected: OK (test_curate_limits·test_objectivity·test_failure_log·test_fallback 전부).

- [ ] **Step 6: Commit**

```bash
git add src/summarize.py tests/test_fallback.py
git commit -m "feat: 실패 기사 제외 + 실패 로그 저장·알림 + 가드에 call_error 포함

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: daily.yml·gitignore 연결 + 실제 검증

**Files:**
- Modify: `.github/workflows/daily.yml`
- Modify: `.gitignore`

- [ ] **Step 1: daily.yml 자동커밋에 failures/ 포함**

`.github/workflows/daily.yml` — `git add News/`를 다음으로 변경:
```yaml
          git add News/ failures/
```
(커밋 메시지·diff 체크는 그대로. failures/가 없거나 비면 add 무시되고 diff 체크가 처리.)

- [ ] **Step 2: .gitignore에 failures/ 추적 예외 주석**

`.gitignore` — `scores/` 주석 아래(또는 raw/selected 블록 아래)에 추가:
```
# failures/ 도 의도적으로 추적한다 — 실패·에러 로그는 누적 자산(추출기 개선 연료).
```

- [ ] **Step 3: 실제 재현 검증 (경제=10, 07-01)**

Run: `python3 src/curate.py 2026-07-01 >/dev/null && python3 src/summarize.py 2026-07-01 2>&1 | tail -8`
Expected: 끝에 `⚠ 실패 N건 — 기록: .../failures/failures-2026-07-01.json`,
칼럼 기사가 실패 목록에 나옴(reason api_failed 또는 call_error).

Run: `python3 -c "import json; d=json.load(open('failures/failures-2026-07-01.json')); print(d['failed_count'], [f['reason'] for f in d['failures']])"`
Expected: 실패 건수와 reason 출력.

Run: `grep -c "권용훈의 트렌드워치\|통곡" News/2026-07-01.md || echo 0`
Expected: `0` (실패 칼럼이 다이제스트 본문에서 제외됨).

- [ ] **Step 4: 실패 0건 케이스 확인**

Run: `rm -f failures/failures-2026-06-30.json; python3 src/curate.py 2026-06-30 >/dev/null && python3 src/summarize.py 2026-06-30 >/dev/null 2>&1; ls failures/failures-2026-06-30.json 2>&1 || echo "실패 0건 → 파일 없음(정상)"`
Expected: 30일 실패가 0건이면 "파일 없음(정상)". (실패가 있으면 파일 생성 — 그 경우도 정상)

- [ ] **Step 5: 격리 확인**

Run: `git diff --stat src/curate.py src/objectivity.py`
Expected: 출력 없음(무변경).

- [ ] **Step 6: 검증 아티팩트 되돌리기 + 커밋**

검증으로 바뀐 News/*.md는 되돌린다(07-01은 자동커밋본 유지):
```bash
git checkout -- News/2026-07-01.md News/2026-06-30.md 2>/dev/null || true
```
설정 변경과 그날 실패 로그를 커밋:
```bash
git add .github/workflows/daily.yml .gitignore failures/
git commit -m "feat: daily 자동커밋에 failures/ 포함 + 추적 예외

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review 결과

**Spec coverage:**
- 실패 제외(§2,§7) → Task 3 render_item·build_markdown ✅
- 원인 구분 call_error(§4) → Task 2 ✅
- 실패 로그 저장·0건 미생성(§5) → Task 1 ✅
- run 수집·저장·알림·가드(§6) → Task 3 ✅
- daily 연결·gitignore(§8) → Task 4 ✅
- 격리(§8) → Task 4 Step 5 ✅
- 테스트(§9) → Task 1·2·3 각 테스트 ✅
- 완료 조건(§10) → Task 4 검증 ✅

**Placeholder scan:** 없음. 모든 코드 스텝에 실제 코드.

**Type consistency:** `summarize_item`→5-튜플이 Task 2 정의·Task 3 run 사용·모든 테스트에서 일치.
`save_failure_log(date, total, failures)`가 Task 1 정의·Task 3 호출에서 일치.
`build_markdown(selected, results, counters)` 시그니처 유지, results는 성공 항목만.
counters 키에 `call_error` 추가가 run·build_markdown·테스트에서 일관.
`render_item`은 인자에서 status 제거(성공 전용) — Task 3 정의·build_markdown 호출 일치.
