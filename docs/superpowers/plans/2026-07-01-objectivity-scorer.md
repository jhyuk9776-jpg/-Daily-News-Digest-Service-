# 매체 객관성 점수 축적기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 요약하지 않은 수집 기사까지 감점 휴리스틱으로 채점해 매체별 객관성 점수를 이동평균으로 누적하는 observe-only 도구를 만든다.

**Architecture:** 독립 모듈 `src/objectivity.py`가 raw JSON을 읽어 기사별 감점 점수를 매기고, 매체별 EWMA로 `scores/media.json`에 누적한다. curate/summarize와 격리되고 daily 파이프라인에 연결하지 않는다. 사용자가 CLI 또는 전용 스킬로 수동 실행한다.

**Tech Stack:** Python 3.9 표준 라이브러리(json, re, datetime, pathlib, argparse) + 기존 `src/curate.py`의 `in_date_window` 재사용. 테스트는 표준 `unittest`.

## Global Constraints

- Python 3.9 호환 (프로젝트 실행 환경 Python 3.9.6). 3.10+ 문법 금지(match문, `X | Y` 런타임 타입 등). 타입힌트는 `from __future__ import annotations`로 처리.
- observe-only: curate/summarize/run.sh/daily.yml 무변경. objectivity는 `curate.in_date_window`만 import.
- KST 기준 날짜: `timezone(timedelta(hours=9))`.
- 상수 기본값(튜닝 대상): `BASELINE=100`, `PENALTY=10`, `FLOOR=0`, `EWMA_ALPHA=0.1`.
- 감점 사전은 고정밀 시드만: PENALTY_PHRASES 4개(§6) + PENALTY_PATTERNS "~가 다 했네" 류. 단일 모호어 금지.
- 테스트 실행: `python3 -m unittest discover -s tests`.
- 커밋 트레일러: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## File Structure

- Create: `src/objectivity.py` — 채점 + EWMA 집계 + 저장 + CLI (단일 책임: 객관성 점수 축적)
- Create: `tests/test_objectivity.py` — 단위 테스트
- Create: `.claude/skills/objectivity-score/SKILL.md` — 수동 실행 전용 스킬
- Modify: `.gitignore` — `scores/`가 무시되지 않게 유지(명시적 예외 주석). raw/·selected/는 그대로
- 런타임 생성(코드 아님): `scores/media.json`, `scores/articles-YYYY-MM-DD.json`

---

## Task 1: 기사별 감점 채점 `objectivity_score`

**Files:**
- Create: `src/objectivity.py`
- Test: `tests/test_objectivity.py`

**Interfaces:**
- Consumes: 없음(신규)
- Produces:
  - `BASELINE=100`, `PENALTY=10`, `FLOOR=0`, `EWMA_ALPHA=0.1` (모듈 상수)
  - `PENALTY_PHRASES: list[str]`, `PENALTY_PATTERNS: list[re.Pattern]`
  - `objectivity_score(article: dict) -> dict` — 반환 `{"score": int, "hits": list[str]}`.
    `article`은 최소 `title`, `summary` 키를 가진 dict. 대상 텍스트 = `title + " " + summary`.
    감점 근거 `hits`는 매칭된 문구/패턴 설명 문자열.

- [ ] **Step 1: Write the failing test**

`tests/test_objectivity.py`:
```python
"""매체 객관성 점수 축적기 테스트 (표준 unittest, 네트워크/API 미사용)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import objectivity  # noqa: E402


class ScoreTest(unittest.TestCase):
    def test_clean_title_is_baseline(self):
        art = {"title": "6월 무역수지 361억달러 흑자", "summary": ""}
        r = objectivity.objectivity_score(art)
        self.assertEqual(r["score"], 100)
        self.assertEqual(r["hits"], [])

    def test_phrase_penalized(self):
        art = {"title": "논란이 커지고 있다는 지적", "summary": ""}
        r = objectivity.objectivity_score(art)
        self.assertEqual(r["score"], 90)
        self.assertIn("논란이 커지고 있다", r["hits"])

    def test_multiple_hits_stack(self):
        art = {"title": "충격을 주고 있다", "summary": "큰 파장이 예상된다"}
        r = objectivity.objectivity_score(art)
        self.assertEqual(r["score"], 80)
        self.assertEqual(len(r["hits"]), 2)

    def test_pattern_match(self):
        art = {"title": "정부가 다 했네", "summary": ""}
        r = objectivity.objectivity_score(art)
        self.assertLess(r["score"], 100)
        self.assertTrue(r["hits"])

    def test_floor_clamp(self):
        # 감점이 아무리 쌓여도 FLOOR(0) 미만으로 내려가지 않는다.
        text = "논란이 커지고 있다 " * 20
        art = {"title": text, "summary": ""}
        r = objectivity.objectivity_score(art)
        self.assertEqual(r["score"], 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_objectivity.ScoreTest -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'objectivity'`

- [ ] **Step 3: Write minimal implementation**

`src/objectivity.py`:
```python
"""Phase 2: 매체 객관성 점수 축적기 (observe-only, record-only).

요약하지 않은 수집 기사까지 감점 휴리스틱으로 채점해 매체별 객관성 점수를
이동평균(EWMA)으로 누적한다. 선별·랭킹에는 반영하지 않는다(관찰만).

설계: docs/superpowers/specs/2026-07-01-objectivity-scorer-design.md
감점 사전 시드: AI_CONTEXT.md §6 "피해야 할 표현".

실행:
    python3 src/objectivity.py            # 오늘(KST) 채점·누적
    python3 src/objectivity.py 2026-06-30 # 특정 날짜
    python3 src/objectivity.py --backfill # raw/*.json 전부 재구축
"""

from __future__ import annotations

import re

BASELINE = 100
PENALTY = 10
FLOOR = 0
EWMA_ALPHA = 0.1

# 감점 사전(고정밀 시드). 단일 모호어("충격" 단독 등)는 오탐 위험으로 제외.
PENALTY_PHRASES = [
    "논란이 커지고 있다",
    "충격을 주고 있다",
    "큰 파장이 예상된다",
    "업계가 주목하고 있다",
]
PENALTY_PATTERNS = [
    re.compile(r"[가-힣]+가 다 했네"),  # "~가 다 했네" 류 평가·조롱
]


def objectivity_score(article: dict) -> dict:
    """기사 1건의 객관성 점수(감점 중심)와 감점 근거를 계산한다."""
    text = f"{article.get('title', '')} {article.get('summary', '')}"
    hits: list[str] = []
    for phrase in PENALTY_PHRASES:
        if phrase in text:
            hits.append(phrase)
    for pat in PENALTY_PATTERNS:
        m = pat.search(text)
        if m:
            hits.append(m.group(0))
    score = max(FLOOR, BASELINE - PENALTY * len(hits))
    return {"score": score, "hits": hits}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_objectivity.ScoreTest -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/objectivity.py tests/test_objectivity.py
git commit -m "feat: 기사별 객관성 감점 채점 objectivity_score

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 매체 EWMA 집계 `update_media_scores`

**Files:**
- Modify: `src/objectivity.py`
- Test: `tests/test_objectivity.py`

**Interfaces:**
- Consumes: `objectivity_score`, `EWMA_ALPHA` (Task 1)
- Produces:
  - `update_media_scores(store: dict, dated_articles: list[dict], date: str) -> dict`
    - `store`: `{"media": {source: {"score": float, "count": int, "penalized": int, "last_seen": str}}, "processed_dates": [str]}`
    - `dated_articles`: 채점 대상 기사 리스트(각 dict에 `title`, `summary`, `source` 포함)
    - `date`: 처리 날짜 문자열 "YYYY-MM-DD"
    - 동작: 이미 `store["processed_dates"]`에 `date`가 있으면 store를 **그대로 반환**(멱등).
      아니면 매체별 그날 평균을 EWMA로 반영, count·penalized 누적, last_seen 갱신,
      date를 processed_dates에 추가. 처음 보는 매체는 그날 평균을 초기 score로.
    - 반환: 갱신된 store (입력 store를 변형해도 됨)

- [ ] **Step 1: Write the failing test**

`tests/test_objectivity.py`에 추가:
```python
class MediaAggregateTest(unittest.TestCase):
    def _empty_store(self):
        return {"media": {}, "processed_dates": []}

    def test_new_media_uses_day_average_as_initial(self):
        arts = [
            {"title": "깨끗한 기사", "summary": "", "source": "한국경제"},
            {"title": "논란이 커지고 있다", "summary": "", "source": "한국경제"},
        ]  # 점수 100, 90 → 그날 평균 95
        store = objectivity.update_media_scores(self._empty_store(), arts, "2026-07-01")
        m = store["media"]["한국경제"]
        self.assertAlmostEqual(m["score"], 95.0)
        self.assertEqual(m["count"], 2)
        self.assertEqual(m["penalized"], 1)
        self.assertEqual(m["last_seen"], "2026-07-01")

    def test_ewma_blends_with_existing(self):
        store = {
            "media": {"한국경제": {"score": 92.0, "count": 10, "penalized": 0,
                                   "last_seen": "2026-06-30"}},
            "processed_dates": ["2026-06-30"],
        }
        arts = [{"title": "깨끗", "summary": "", "source": "한국경제"}]  # 그날 평균 100
        store = objectivity.update_media_scores(store, arts, "2026-07-01")
        # 0.9*92 + 0.1*100 = 92.8
        self.assertAlmostEqual(store["media"]["한국경제"]["score"], 92.8)
        self.assertEqual(store["media"]["한국경제"]["count"], 11)

    def test_idempotent_same_date_skipped(self):
        arts = [{"title": "깨끗", "summary": "", "source": "한국경제"}]
        store = objectivity.update_media_scores(self._empty_store(), arts, "2026-07-01")
        before = objectivity_snapshot(store)
        store = objectivity.update_media_scores(store, arts, "2026-07-01")
        self.assertEqual(objectivity_snapshot(store), before)


def objectivity_snapshot(store):
    import json
    return json.dumps(store, sort_keys=True, ensure_ascii=False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_objectivity.MediaAggregateTest -v`
Expected: FAIL — `AttributeError: module 'objectivity' has no attribute 'update_media_scores'`

- [ ] **Step 3: Write minimal implementation**

`src/objectivity.py`에 추가:
```python
def update_media_scores(store: dict, dated_articles: list[dict], date: str) -> dict:
    """그날 기사들을 매체별로 채점해 EWMA로 store에 누적한다(멱등)."""
    if date in store.get("processed_dates", []):
        return store  # 이미 처리한 날짜 — 이중 반영 방지

    # 매체별 그날 점수 모으기
    by_source: dict[str, list[int]] = {}
    penalized: dict[str, int] = {}
    for art in dated_articles:
        source = art.get("source", "")
        r = objectivity_score(art)
        by_source.setdefault(source, []).append(r["score"])
        if r["hits"]:
            penalized[source] = penalized.get(source, 0) + 1

    media = store.setdefault("media", {})
    for source, scores in by_source.items():
        day_avg = sum(scores) / len(scores)
        if source in media:
            prev = media[source]
            prev["score"] = (1 - EWMA_ALPHA) * prev["score"] + EWMA_ALPHA * day_avg
            prev["count"] += len(scores)
            prev["penalized"] += penalized.get(source, 0)
            prev["last_seen"] = date
        else:
            media[source] = {
                "score": day_avg,
                "count": len(scores),
                "penalized": penalized.get(source, 0),
                "last_seen": date,
            }

    store.setdefault("processed_dates", []).append(date)
    return store
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_objectivity.MediaAggregateTest -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/objectivity.py tests/test_objectivity.py
git commit -m "feat: 매체 EWMA 집계 update_media_scores (멱등)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 저장 I/O + 날짜 기사 로딩

**Files:**
- Modify: `src/objectivity.py`
- Test: `tests/test_objectivity.py`

**Interfaces:**
- Consumes: `curate.in_date_window`, `update_media_scores` (Task 2)
- Produces:
  - `KST` (timezone), `ROOT`, `RAW_DIR`, `SCORES_DIR`, `MEDIA_FILE` (Path 상수)
  - `load_store() -> dict` — `scores/media.json` 읽기. 없으면 `{"media": {}, "processed_dates": []}`
  - `save_store(store: dict) -> None` — `scores/media.json` 쓰기(디렉터리 자동 생성, `updated_at` 갱신)
  - `save_article_report(date: str, records: list[dict]) -> None` —
    감점받은 기사(score<100)만 `scores/articles-<date>.json`에 저장.
    `records` 각 항목: `{"source","category","title","link","score","hits"}`
  - `dated_articles_for(date: str) -> list[dict]` — `raw/<date>.json`을 읽어
    `in_date_window` 통과 기사 리스트 반환. 파일 없으면 `FileNotFoundError`.
    **중요:** 날짜창 기준을 `now()`가 아니라 **그 raw 파일의 날짜(date)**로 잡는다.
    그래야 나중에 과거 파일을 재백필해도 오늘·어제 창 밖이라 걸러지지 않는다.

- [ ] **Step 1: Write the failing test**

`tests/test_objectivity.py`에 추가:
```python
import json
import tempfile
from pathlib import Path
from unittest.mock import patch


class StoreIOTest(unittest.TestCase):
    def test_load_missing_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(objectivity, "MEDIA_FILE", Path(tmp) / "media.json"):
                store = objectivity.load_store()
        self.assertEqual(store, {"media": {}, "processed_dates": []})

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            mf = Path(tmp) / "media.json"
            with patch.object(objectivity, "MEDIA_FILE", mf), \
                 patch.object(objectivity, "SCORES_DIR", Path(tmp)):
                objectivity.save_store({"media": {"A": {"score": 90.0, "count": 1,
                                       "penalized": 0, "last_seen": "2026-07-01"}},
                                       "processed_dates": ["2026-07-01"]})
                store = objectivity.load_store()
        self.assertEqual(store["media"]["A"]["score"], 90.0)
        self.assertIn("updated_at", store)

    def test_article_report_saves_only_penalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(objectivity, "SCORES_DIR", Path(tmp)):
                objectivity.save_article_report("2026-07-01", [
                    {"source": "A", "category": "경제", "title": "논란이 커지고 있다",
                     "link": "L1", "score": 90, "hits": ["논란이 커지고 있다"]},
                ])
                data = json.loads((Path(tmp) / "articles-2026-07-01.json").read_text())
        self.assertEqual(data["penalized_count"], 1)
        self.assertEqual(data["articles"][0]["source"], "A")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_objectivity.StoreIOTest -v`
Expected: FAIL — `AttributeError: module 'objectivity' has no attribute 'MEDIA_FILE'`

- [ ] **Step 3: Write minimal implementation**

`src/objectivity.py` 상단 import·상수 추가:
```python
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from curate import in_date_window  # 날짜창 필터 재사용(격리: 단방향 의존)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw"
SCORES_DIR = ROOT / "scores"
MEDIA_FILE = SCORES_DIR / "media.json"
KST = timezone(timedelta(hours=9))
```

`src/objectivity.py`에 함수 추가:
```python
def load_store() -> dict:
    if MEDIA_FILE.exists():
        with MEDIA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"media": {}, "processed_dates": []}


def save_store(store: dict) -> None:
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    store["updated_at"] = datetime.now(KST).isoformat(timespec="seconds")
    with MEDIA_FILE.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def save_article_report(date: str, records: list[dict]) -> None:
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    penalized = [r for r in records if r["score"] < BASELINE]
    payload = {
        "date": date,
        "scored": len(records),
        "penalized_count": len(penalized),
        "articles": penalized,
    }
    with (SCORES_DIR / f"articles-{date}.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def dated_articles_for(date: str) -> list[dict]:
    path = RAW_DIR / f"{date}.json"
    if not path.exists():
        raise FileNotFoundError(f"수집 결과가 없음: {path} (먼저 fetch.py 실행)")
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    # 날짜창 기준은 now()가 아니라 그 raw 파일의 날짜(정오 KST). 재백필 시 과거 파일도 정확.
    ref = datetime.fromisoformat(date).replace(tzinfo=KST) + timedelta(hours=12)
    return [a for a in raw["articles"] if in_date_window(a, ref)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_objectivity.StoreIOTest -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/objectivity.py tests/test_objectivity.py
git commit -m "feat: scores 저장 I/O + 날짜 기사 로딩(in_date_window 재사용)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 하루 처리 오케스트레이션 + CLI + 백필

**Files:**
- Modify: `src/objectivity.py`
- Test: `tests/test_objectivity.py`

**Interfaces:**
- Consumes: `dated_articles_for`, `update_media_scores`, `save_article_report`,
  `load_store`, `save_store`, `objectivity_score`, `RAW_DIR`, `KST` (Tasks 1-3)
- Produces:
  - `process_date(store: dict, date: str) -> dict` — `dated_articles_for(date)`로 기사를 얻어
    `update_media_scores`로 store 갱신, 감점 리포트 저장. store 반환.
    (멱등성은 update_media_scores가 담당: 이미 처리한 날짜면 리포트도 다시 쓰지 않음)
  - `run_backfill() -> dict` — `raw/*.json`을 날짜 오름차순으로 전부 처리. store를 빈 상태에서
    새로 구축(전체 재구축)하고 저장. store 반환.
  - `main() -> int` — argparse. `--backfill`이면 `run_backfill`, 아니면 인자 날짜(기본 오늘 KST)로
    `process_date` 후 저장. 요약 통계 출력.

- [ ] **Step 1: Write the failing test**

`tests/test_objectivity.py`에 추가:
```python
class ProcessAndBackfillTest(unittest.TestCase):
    def _write_raw(self, raw_dir, date, articles):
        payload = {"date": date, "articles": articles}
        (raw_dir / f"{date}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _art(self, source, title, iso):
        return {"category": "경제", "source": source, "title": title,
                "summary": "", "link": f"L-{title}", "published_iso": iso}

    def test_process_date_updates_store_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            raw_dir = tmp_p / "raw"; raw_dir.mkdir()
            # 오늘 날짜를 고정하기 위해 window를 넉넉히: iso를 오늘로
            today = datetime.now(objectivity.KST).date().isoformat()
            self._write_raw(raw_dir, today, [
                self._art("한국경제", "깨끗한 기사", f"{today}T01:00:00+00:00"),
                self._art("한국경제", "논란이 커지고 있다", f"{today}T01:00:00+00:00"),
            ])
            with patch.object(objectivity, "RAW_DIR", raw_dir), \
                 patch.object(objectivity, "SCORES_DIR", tmp_p / "scores"), \
                 patch.object(objectivity, "MEDIA_FILE", tmp_p / "scores" / "media.json"):
                store = objectivity.process_date(
                    {"media": {}, "processed_dates": []}, today)
                self.assertIn("한국경제", store["media"])
                self.assertEqual(store["media"]["한국경제"]["count"], 2)
                report = json.loads(
                    (tmp_p / "scores" / f"articles-{today}.json").read_text())
                self.assertEqual(report["penalized_count"], 1)

    def test_backfill_processes_old_files(self):
        # 과거 날짜(오래된 raw)도 걸러지지 않고 처리돼야 한다(now()가 아니라 파일 날짜 기준).
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            raw_dir = tmp_p / "raw"; raw_dir.mkdir()
            old = "2020-01-15"  # 한참 과거 — now() 기준이면 전부 걸러질 날짜
            self._write_raw(raw_dir, old, [
                self._art("A", "깨끗", "2020-01-15T01:00:00+00:00")])
            with patch.object(objectivity, "RAW_DIR", raw_dir), \
                 patch.object(objectivity, "SCORES_DIR", tmp_p / "scores"), \
                 patch.object(objectivity, "MEDIA_FILE", tmp_p / "scores" / "media.json"):
                store = objectivity.run_backfill()
        self.assertIn(old, store["processed_dates"])
        self.assertIn("A", store["media"])  # 파일 날짜 기준이라 통과
        self.assertEqual(store["media"]["A"]["count"], 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_objectivity.ProcessAndBackfillTest -v`
Expected: FAIL — `AttributeError: module 'objectivity' has no attribute 'process_date'`

- [ ] **Step 3: Write minimal implementation**

`src/objectivity.py`에 추가:
```python
def process_date(store: dict, date: str) -> dict:
    """하루치 raw를 채점해 store에 누적하고 감점 리포트를 저장한다."""
    articles = dated_articles_for(date)
    already = date in store.get("processed_dates", [])
    store = update_media_scores(store, articles, date)
    if not already:
        records = []
        for a in articles:
            r = objectivity_score(a)
            records.append({
                "source": a.get("source", ""),
                "category": a.get("category", ""),
                "title": a.get("title", ""),
                "link": a.get("link", ""),
                "score": r["score"],
                "hits": r["hits"],
            })
        save_article_report(date, records)
    return store


def run_backfill() -> dict:
    """raw/*.json을 날짜 오름차순으로 전부 재처리해 store를 새로 구축한다."""
    store = {"media": {}, "processed_dates": []}
    dates = sorted(p.stem for p in RAW_DIR.glob("*.json"))
    for date in dates:
        store = process_date(store, date)
    save_store(store)
    print(f"백필 완료: {len(dates)}일 처리, 매체 {len(store['media'])}곳")
    return store


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="매체 객관성 점수 축적기(observe-only)")
    parser.add_argument("date", nargs="?", help="처리할 날짜 YYYY-MM-DD (기본: 오늘 KST)")
    parser.add_argument("--backfill", action="store_true",
                        help="raw/*.json 전부 재처리(전체 재구축)")
    args = parser.parse_args()

    if args.backfill:
        run_backfill()
        return 0

    date = args.date or datetime.now(KST).strftime("%Y-%m-%d")
    store = load_store()
    try:
        store = process_date(store, date)
    except FileNotFoundError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    save_store(store)

    print(f"=== 객관성 점수 축적 ({date}) ===")
    for source, m in sorted(store["media"].items(), key=lambda kv: kv[1]["score"]):
        print(f"  {m['score']:5.1f} · {source} "
              f"(표본 {m['count']}, 감점 {m['penalized']})")
    print(f"저장됨: {MEDIA_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_objectivity.ProcessAndBackfillTest -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run full suite + real backfill smoke test**

Run: `python3 -m unittest discover -s tests`
Expected: OK (전체 통과, 기존 test_fallback 포함)

Run: `python3 src/objectivity.py --backfill`
Expected: "백필 완료: N일 처리, 매체 M곳" 출력, `scores/media.json` 생성됨.

- [ ] **Step 6: Commit**

```bash
git add src/objectivity.py tests/test_objectivity.py
git commit -m "feat: 하루 처리·백필·CLI 오케스트레이션

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: scores/ git 추적 + 전용 스킬

**Files:**
- Modify: `.gitignore`
- Create: `.claude/skills/objectivity-score/SKILL.md`

**Interfaces:**
- Consumes: `src/objectivity.py` CLI (Task 4)
- Produces: 없음(문서·설정)

- [ ] **Step 1: .gitignore에 scores/ 추적 예외 명시**

`.gitignore`의 raw/·selected/ 블록 아래에 주석 추가(무시 목록에 scores/를 넣지 않음으로써 추적):
```
# 매일 바뀌는 생성 산출물 (저장소에 쌓지 않음)
raw/
selected/

# scores/ 는 의도적으로 추적한다 — 매체 객관성 점수는 누적 상태라 커밋으로 보존.
```

- [ ] **Step 2: 전용 스킬 작성**

`.claude/skills/objectivity-score/SKILL.md`:
```markdown
---
name: objectivity-score
description: Use when the user asks to accumulate/update media objectivity scores (점수 축적, 객관성 점수 갱신) for this AI 뉴스 프로젝트. Runs the observe-only scorer over collected raw articles and reports media reputation.
---

# 객관성 점수 축적 (수동)

요약하지 않은 수집 기사까지 감점 휴리스틱으로 채점해 매체별 객관성 점수를
이동평균으로 누적한다. observe-only — 선별·랭킹에 반영하지 않는다.
설계: docs/superpowers/specs/2026-07-01-objectivity-scorer-design.md

## 언제
- 사용자가 "점수 축적해줘", "객관성 점수 갱신", "매체 점수 돌려줘"라고 할 때.

## 절차
1. 어떤 범위인지 확인: 오늘 하루인지(`python3 src/objectivity.py`),
   특정 날짜인지(`python3 src/objectivity.py YYYY-MM-DD`),
   전체 재구축인지(`python3 src/objectivity.py --backfill`).
   - 기본은 오늘 하루. 처음이거나 과거분을 다시 반영하려면 --backfill.
2. 실행하고 출력(매체별 점수·표본수·감점수)을 사용자에게 요약 보고한다.
3. `scores/articles-<날짜>.json`의 감점 사례를 몇 건 짚어, 감점 사전 오탐이 있는지
   같이 확인한다(있으면 PENALTY_PHRASES/PATTERNS 조정 후보로 메모).
4. `scores/`를 커밋해 누적을 보존한다:
   `git add scores/ && git commit -m "chore: 객관성 점수 축적 <날짜>"`
   (커밋 전 사용자에게 확인).

## 주의
- observe-only: curate/summarize/run.sh/daily.yml을 건드리지 않는다.
- 멱등: 같은 날짜를 다시 돌려도 이중 반영되지 않는다(--backfill만 전체 재구축).
- 감점 사전은 고정밀 시드다. 단일 모호어("충격" 단독 등)를 함부로 추가하지 않는다.
```

- [ ] **Step 3: 확인 — scores/가 추적되는지, 파이프라인 무변경인지**

Run: `git status --short scores/`
Expected: `scores/media.json`, `scores/articles-*.json`이 추적 대상(`??` 또는 스테이지됨)으로 나타남.

Run: `git diff --stat run.sh .github/workflows/daily.yml src/curate.py src/summarize.py`
Expected: 출력 없음(무변경 — observe-only 격리 확인).

- [ ] **Step 4: Commit**

```bash
git add .gitignore .claude/skills/objectivity-score/SKILL.md scores/
git commit -m "feat: 객관성 점수 전용 스킬 + scores/ git 추적

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review 결과

**Spec coverage:**
- 채점 모델(§4) → Task 1 ✅
- 매체 EWMA 축적(§5) → Task 2 ✅
- 저장 스키마(§6) → Task 3 ✅
- 실행/CLI/백필/멱등(§7) → Task 3(멱등 in update)·Task 4 ✅
- 전용 스킬·scores git 추적(§2,§7) → Task 5 ✅
- 격리 원칙(§8) → Task 3(단방향 import)·Task 5 Step 3(무변경 확인) ✅
- 테스트(§9) → 각 Task의 테스트 + Task 4 전체 스위트 ✅
- 완료 조건(§10) → Task 4 Step 5(백필 스모크)·Task 5 Step 3(격리 확인) ✅

**Placeholder scan:** 없음. 모든 코드 스텝에 실제 코드 포함.

**Type consistency:** `objectivity_score`→`{score,hits}`, `update_media_scores(store,dated_articles,date)`,
`process_date(store,date)`, `dated_articles_for(date)`, store 스키마(media/processed_dates)가
Task 1→5에서 일관. `save_article_report`는 score<BASELINE로 필터(Task 3), records 형태는 Task 4에서 생성하는 dict와 일치.
