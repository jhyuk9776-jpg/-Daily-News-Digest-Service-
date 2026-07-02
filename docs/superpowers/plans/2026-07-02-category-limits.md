# 분야별 요약 상한 (Phase 1.5 선행판) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 분야별 요약 상한을 `limits.yaml` 설정으로 분리해, 분야마다 다른 상한(예: 경제 10건)을 적용하고 파이프라인이 상한까지 정상 동작하는지 검증한다.

**Architecture:** 신규 `limits.yaml`(repo 루트)에 분야별 상한을 두고, `curate.py`가 `load_limits`로 읽어 `select()`에서 `clusters[:분야별_limit]`로 적용한다. 품질 게이트는 없다(Phase 2 본편). `curate.py`와 `limits.yaml`만 변경한다.

**Tech Stack:** Python 3.9 표준 라이브러리 + PyYAML(`yaml`, 기존 사용) + 표준 `unittest`.

## Global Constraints

- Python 3.9 호환. 3.10+ 문법 금지(`X | Y` 등). 아래 코드는 3.9에서 안전한 형태(`dict`, `int` 빌트인 힌트, `= None` 기본값)로 제공했으니 그대로 사용.
- KST 기준 날짜: 기존 `curate.KST` 사용.
- 하위호환: `limits.yaml`이 없으면 `(default=2, {})`로 폴백해 기존 8건 동작 유지.
- observe-only 격리: `summarize.py`·`objectivity.py`·`run.sh`·`.github/workflows/daily.yml` 무변경.
- 테스트 실행: `python3 -m unittest discover -s tests`.
- 커밋 트레일러: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## File Structure

- Create: `limits.yaml` — 분야별 요약 상한 설정(repo 루트)
- Create: `tests/test_curate_limits.py` — 상한 로더·선별 단위 테스트
- Modify: `src/curate.py` — `LIMITS_FILE` 상수, `load_limits()` 추가, `select()`에 상한 인자, `main()` 배선, `PER_CATEGORY` 상수 제거

---

## Task 1: 상한 설정 로더 `load_limits` + limits.yaml

**Files:**
- Create: `limits.yaml`
- Modify: `src/curate.py` (상수 `LIMITS_FILE`, 함수 `load_limits`)
- Test: `tests/test_curate_limits.py`

**Interfaces:**
- Consumes: 없음(기존 `yaml`, `Path` 사용)
- Produces:
  - `LIMITS_FILE = ROOT / "limits.yaml"` (모듈 상수)
  - `load_limits(path)` → `(default_limit, per_category_limits)` 튜플.
    `default_limit`: int, `per_category_limits`: dict[str,int]. 파일 없으면 `(2, {})`.

- [ ] **Step 1: Write the failing test**

`tests/test_curate_limits.py`:
```python
"""분야별 요약 상한(Phase 1.5) 테스트 (표준 unittest, 네트워크/API 미사용)."""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import curate  # noqa: E402


class LoadLimitsTest(unittest.TestCase):
    def test_parses_default_and_per_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "limits.yaml"
            p.write_text("default: 2\nper_category:\n  경제: 10\n", encoding="utf-8")
            default, per_cat = curate.load_limits(p)
        self.assertEqual(default, 2)
        self.assertEqual(per_cat, {"경제": 10})

    def test_missing_file_falls_back(self):
        default, per_cat = curate.load_limits(Path("/nonexistent/limits.yaml"))
        self.assertEqual(default, 2)
        self.assertEqual(per_cat, {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_curate_limits.LoadLimitsTest -v`
Expected: FAIL — `AttributeError: module 'curate' has no attribute 'load_limits'`

- [ ] **Step 3: Write minimal implementation**

`src/curate.py` — 상수 블록(현재 `SELECTED_DIR = ROOT / "selected"` 아래)에 추가:
```python
LIMITS_FILE = ROOT / "limits.yaml"
```

`src/curate.py` — `load_priority_map` 함수 아래에 추가:
```python
def load_limits(path: Path):
    """분야별 요약 상한을 읽는다. 반환 (default_limit, per_category_limits).

    파일이 없거나 비어 있으면 (2, {})로 폴백해 기존 동작(분야별 2건)을 유지한다.
    """
    if not path.exists():
        return 2, {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    default = data.get("default", 2)
    per_category = data.get("per_category", {}) or {}
    return default, per_category
```

Create `limits.yaml` (repo 루트):
```yaml
# 분야별 요약 상한(선별 최대 개수). 품질 게이트는 Phase 2 본편에서 추가.
# 후보가 상한보다 적으면 있는 만큼만 나온다(억지로 채우지 않음).
default: 2
per_category:
  경제: 10
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_curate_limits.LoadLimitsTest -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add limits.yaml src/curate.py tests/test_curate_limits.py
git commit -m "feat: 분야별 요약 상한 로더 load_limits + limits.yaml

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: select()에 분야별 상한 적용 + main 배선 + PER_CATEGORY 제거

**Files:**
- Modify: `src/curate.py` (`select` 시그니처·본문, `main`, `PER_CATEGORY` 제거)
- Test: `tests/test_curate_limits.py`

**Interfaces:**
- Consumes: `load_limits` (Task 1), 기존 `cluster_articles`, `in_date_window`, `recency_key`
- Produces:
  - `select(raw, priority_map, today, default_limit=2, per_category_limits=None)` →
    기존과 동일 구조 dict. 분야별 `limit = per_category_limits.get(category, default_limit)`,
    `selected = clusters[:limit]`.

- [ ] **Step 1: Write the failing test**

`tests/test_curate_limits.py`에 추가(파일 하단):
```python
KST = timezone(timedelta(hours=9))

# 서로 유사도 0.6 미만이 되도록 겹치지 않는 제목들(클러스터가 각각 분리되게).
ECON_TITLES = [
    "무역흑자", "금리동결", "반도체수출", "부동산대책", "환율급등", "국채발행",
    "소비자물가", "고용지표", "코스피상승", "유가하락", "세수부족", "가계부채",
]
SOCIAL_TITLES = ["학교폭력", "교통사고", "의료파업"]


def _art(category, source, title, iso):
    return {"category": category, "source": source, "title": title,
            "summary": "", "link": f"L-{title}", "published_iso": iso}


class SelectLimitTest(unittest.TestCase):
    def _raw(self):
        iso = "2026-07-02T01:00:00+00:00"
        arts = [_art("경제", "한국경제", t, iso) for t in ECON_TITLES]
        arts += [_art("사회", "경향신문", t, iso) for t in SOCIAL_TITLES]
        return {"date": "2026-07-02", "articles": arts}

    def _today(self):
        return datetime(2026, 7, 2, 12, 0, tzinfo=KST)

    def _priority(self):
        return {("경제", "한국경제"): 1, ("사회", "경향신문"): 1}

    def test_per_category_cap_applied(self):
        # 경제 후보 12개 + 상한 10 → 경제 10개, 사회는 default 2
        result = curate.select(self._raw(), self._priority(), self._today(),
                               default_limit=2, per_category_limits={"경제": 10})
        self.assertEqual(len(result["categories"]["경제"]), 10)
        self.assertEqual(len(result["categories"]["사회"]), 2)

    def test_fewer_candidates_than_cap(self):
        # 경제 후보 12개인데 상한 20 → 있는 12개만(빈 채움 없음)
        result = curate.select(self._raw(), self._priority(), self._today(),
                               default_limit=2, per_category_limits={"경제": 20})
        self.assertEqual(len(result["categories"]["경제"]), 12)

    def test_default_when_no_config(self):
        # per_category_limits 미지정 → 모든 분야 default 2
        result = curate.select(self._raw(), self._priority(), self._today())
        self.assertEqual(len(result["categories"]["경제"]), 2)
        self.assertEqual(len(result["categories"]["사회"]), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_curate_limits.SelectLimitTest -v`
Expected: FAIL — `TypeError: select() got an unexpected keyword argument 'default_limit'`

- [ ] **Step 3: Write minimal implementation**

`src/curate.py` — `select` 시그니처 변경 (현재 `def select(raw: dict, priority_map: dict, today: datetime) -> dict:`):
```python
def select(raw: dict, priority_map: dict, today: datetime,
           default_limit: int = 2, per_category_limits: dict = None) -> dict:
    if per_category_limits is None:
        per_category_limits = {}
```

`src/curate.py` — `select` 본문에서 슬라이스 부분(현재 `selected = clusters[:PER_CATEGORY]`) 변경:
```python
        limit = per_category_limits.get(category, default_limit)
        selected = clusters[:limit]
```

`src/curate.py` — `PER_CATEGORY = 2 ...` 상수 줄 삭제(더 이상 참조 없음).

`src/curate.py` — `main()`에서 `select` 호출부(현재 `result = select(raw, priority_map, today)`) 변경:
```python
    default_limit, per_category_limits = load_limits(LIMITS_FILE)
    result = select(raw, priority_map, today, default_limit, per_category_limits)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_curate_limits.SelectLimitTest -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run full suite (회귀 확인)**

Run: `python3 -m unittest discover -s tests`
Expected: OK (신규 + 기존 test_curate*/test_fallback/test_objectivity 전부 통과).
`PER_CATEGORY` 제거로 깨지는 곳이 없는지 확인 — 실패 시 `grep -rn PER_CATEGORY src/`로 잔존 참조 제거.

- [ ] **Step 6: Commit**

```bash
git add src/curate.py tests/test_curate_limits.py
git commit -m "feat: select에 분야별 상한 적용 + main 배선, PER_CATEGORY 제거

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 실제 파이프라인 검증 (경제=10 스모크)

**Files:**
- (코드 변경 없음. 실행·관찰만. 필요 시 `limits.yaml` 값 조정)

**Interfaces:**
- Consumes: Task 1·2 결과 + 기존 `raw/*.json`

- [ ] **Step 1: 최신 raw 확인**

Run: `ls raw/`
Expected: `2026-07-01.json` 등 최소 1개 존재. (없으면 `python3 src/fetch.py`로 생성)

- [ ] **Step 2: 경제=10으로 선별 실행, 상한 반영 확인**

Run: `python3 src/curate.py 2026-07-01`
Expected: 출력의 `[경제] ... → 선택 N`에서 N이 2보다 큼(가용 클러스터가 10 이상이면 10, 미만이면 그만큼). 사회/세계/IT는 2.

- [ ] **Step 3: 요약 실행, 상한까지 요약·가드 미발동 확인**

Run: `python3 src/summarize.py 2026-07-01`
Expected: `News/2026-07-01.md` 경제 섹션이 상한(가용분)까지 채워짐. 종료코드 0(요약 과반 실패 가드 미발동). 429가 나와도 자동 재시도로 완료.

Run: `echo "exit=$?"` (직전 명령 종료코드)
Expected: `exit=0`

- [ ] **Step 4: 하위호환 폴백 확인**

Run: `mv limits.yaml /tmp/limits.yaml && python3 src/curate.py 2026-07-01`
Expected: `[경제] ... → 선택 2` (파일 없으면 default 2로 폴백).
Run: `mv /tmp/limits.yaml limits.yaml` (원위치)

- [ ] **Step 5: 격리 확인 (파이프라인 무변경)**

Run: `git diff --stat src/summarize.py src/objectivity.py run.sh .github/workflows/daily.yml`
Expected: 출력 없음(무변경).

- [ ] **Step 6: 검증 결과에 따라 limits.yaml 값 확정 후 커밋(선택)**

경제=10 유지가 맞다면 이미 Task 1에서 커밋됨. 검증 중 값을 바꿨다면:
```bash
git add limits.yaml
git commit -m "chore: 분야별 상한 검증 후 값 확정

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review 결과

**Spec coverage:**
- 설정 파일 limits.yaml(§4) → Task 1 ✅
- 로더 load_limits + 폴백(§5) → Task 1 ✅
- select 분야별 상한 적용(§5) → Task 2 ✅
- main 배선 → Task 2 ✅
- 후보<상한 min 동작 / 빈 섹션(§3) → Task 2 test_fewer_candidates_than_cap ✅
- 하위호환 폴백(§3) → Task 1 test + Task 3 Step 4 ✅
- 격리(§2) → Task 3 Step 5 ✅
- 실제 상한까지 요약 검증(§8) → Task 3 ✅

**Placeholder scan:** 없음. 모든 코드 스텝에 실제 코드·명령 포함.

**Type consistency:** `load_limits`→`(int, dict)` 반환이 Task 1 정의와 Task 2 main 사용에서 일치.
`select(..., default_limit, per_category_limits)` 시그니처가 Task 2 정의·테스트·main 호출에서 일치.
`per_category_limits.get(category, default_limit)` 키 타입(분야명 str) 일관.
