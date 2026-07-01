# 매체 객관성 점수 축적기 (record-only) 설계

- 작성일: 2026-07-01
- 작성자: 이재혁
- 상태: 설계 확정, 구현 대기
- 관련: 로드맵 6절(매체 객관성 동적 점수 / 빠른 안정화: 전량 record-only 스코어링),
  결정 로그 1.3(객관성 예시 1호·감점 예시 1호), AI_CONTEXT §6(피해야 할 표현)

## 1. 배경 / 목적

객관성 점수 시스템의 연료는 라벨 데이터다. 요약 대상은 하루 8건뿐이라 매체 점수가
느리게 수렴한다. 시간 제약상 빨리 안정화하기 위해, **요약(AI 호출) 없이** 수집·날짜필터
통과 기사 전량(하루 ~1100건)의 제목·RSS 요약에 감점 휴리스틱을 적용해 **점수만 축적**한다.

**observe-only.** 이 점수는 선별·랭킹에 반영하지 않는다. 분포가 쌓이면 그때 임계값을
데이터로 정한다(로드맵 6절 방향).

## 2. 범위

포함:
- 기사별 객관성 점수(감점 중심) 계산
- 매체(source)별 이동평균 축적
- 하루 실행 + 기존 raw 백필
- **수동 실행**: CLI + 전용 스킬(`.claude/skills/`)로 사용자가 필요할 때 돌림
- `scores/`를 git 추적해 수동 실행 결과를 커밋으로 누적
- 테스트

제외(비목표):
- **daily 파이프라인/CI 연결** (run.sh·daily.yml 손대지 않음). 점수 축적은 요약과
  분리된 수동 작업이다. CI 러너 초기화로 인한 지속성 문제를 원천 회피.
- 선별/랭킹 반영, 자동 제외 (observe-only)
- Supabase 등 DB 저장 (로컬 JSON. 다중 사용자 시점으로 미룸)
- evidence 가점과의 결합 (감점 축과 분리)
- 사용자 라벨(좋은 예시) 파이프라인 (별개 스트림, 이번 범위 아님)
- 본문 추출 기반 정밀 채점 (RSS 제목·요약만 사용)

## 3. 결정 사항 (브레인스토밍 확정)

| 쟁점 | 결정 |
|---|---|
| 채점 단위 | **기사별** (source 유지). 매체 신호를 살려 빠르게 안정화 |
| 점수 축 | **감점 중심** (평가어·홍보성). evidence 가점은 섞지 않음. JB금융("숫자 있는 홍보")이 고득점하는 문제 차단 |
| 매체 집계 | 기사 점수 → 매체 **이동평균**(EWMA, 느린 평판) |
| 감점 사전 | **고정밀 시드로 최소 출발**. 단일 모호어("충격" 등)는 제외, 데이터 보고 확장 |
| 반영 여부 | **observe-only** — 랭킹 무영향 |
| 실행 | **수동** (CLI + 전용 스킬). daily 파이프라인/CI 미연결 |
| 아키텍처 | 독립 모듈 `src/objectivity.py` + `scores/` 저장소 (curate/summarize와 격리) |
| 저장 | 로컬 JSON, **git 추적**(수동 실행 결과를 커밋으로 누적) |

## 4. 채점 모델

`objectivity_score(article) -> {"score": int, "hits": [str]}`

- 대상 텍스트: `title + " " + summary` (summary는 빈 매체 많음 → 제목이 주 신호)
- `BASELINE = 100`에서 시작, 감점사전 매칭마다 `PENALTY` 감점, `FLOOR = 0`으로 클램프
- `hits`: 매칭된 감점 근거 문자열 목록(감사용)

감점 사전(시드, 고정밀):
- `PENALTY_PHRASES` (§6 "피해야 할 표현", 다어절이라 오탐↓):
  - "논란이 커지고 있다"
  - "충격을 주고 있다"
  - "큰 파장이 예상된다"
  - "업계가 주목하고 있다"
- `PENALTY_PATTERNS` (정규식):
  - "~가 다 했네" 류 평가·조롱 (예: `[가-힣]+가 다 했네`)

상수(observe-only, 미확정 튜닝 대상):
- `BASELINE = 100`, `PENALTY = 10`, `FLOOR = 0`, `EWMA_ALPHA = 0.1`

> 단일 모호어("충격", "발칵" 등)는 지진 등 사실 기사 오탐 위험이 커 **초기 시드에서 제외**한다.
> 감점 사전 확장은 축적된 articles-*.json을 보고 데이터 기반으로 한다.

## 5. 데이터 흐름

```
raw/YYYY-MM-DD.json (articles ~1100)
  → in_date_window 필터 (curate에서 재사용)
  → 각 기사 objectivity_score()
  → source별 그날 평균 계산
  → 매체 EWMA 갱신: new = (1-α)·old + α·그날_그매체_평균
  → scores/media.json 저장 (+ 감점 기사 상세는 scores/articles-YYYY-MM-DD.json)
```

EWMA 예: 한국경제 old=92.0, 오늘 40건 평균=88.0, α=0.1 → `0.9·92 + 0.1·88 = 91.6`.
처음 보는 매체는 그날 평균을 초기값으로 둔다.

## 6. 저장 스키마

`scores/media.json` (최종 산출물):
```json
{
  "updated_at": "2026-07-01T16:20:00+09:00",
  "processed_dates": ["2026-06-30", "2026-07-01"],
  "media": {
    "한국경제": {"score": 91.6, "count": 540, "penalized": 12, "last_seen": "2026-07-01"}
  }
}
```
- `count`: 누적 채점 기사 수 · `penalized`: 감점(score<100)받은 기사 수
- `processed_dates`: 멱등성용. 이미 처리한 날짜는 재실행 시 건너뜀

`scores/articles-YYYY-MM-DD.json` (감사용, **감점받은 기사만** 저장해 경량화):
```json
{
  "date": "2026-07-01",
  "scored": 1103,
  "penalized_count": 47,
  "articles": [
    {"source": "전자신문", "category": "IT/테크",
     "title": "...성과 입증", "link": "https://...",
     "score": 90, "hits": ["업계가 주목하고 있다"]}
  ]
}
```

## 7. 실행 / 연결 (수동)

점수 축적은 daily 파이프라인과 **분리된 수동 작업**이다. 요약/CI에 붙이지 않는다.

CLI:
- `python3 src/objectivity.py [YYYY-MM-DD]` — 하루 채점(기본: 오늘 KST)
- `python3 src/objectivity.py --backfill` — `raw/*.json` 전부를 날짜 오름차순 재처리,
  `media.json`을 처음부터 재구축(`processed_dates` 리셋)

전용 스킬(`.claude/skills/objectivity-score/`): 사용자가 "점수 축적해줘"라고 부탁하면
Claude가 (1) CLI 실행 (2) `scores/media.json` 요약 보고 (3) `scores/` 커밋까지 안내·수행.
daily-briefing처럼 사용자 워크플로 스킬.

지속성: `scores/`를 git 추적한다. 수동 실행 후 커밋하면 다음 실행이 그 위에 누적된다.
(raw/·selected/는 gitignore 유지 — 매일 재생성 산출물. scores/만 예외로 추적)

멱등성: `processed_dates`에 있는 날짜면 하루 채점을 건너뛴다. 같은 날짜 재실행 시
이동평균 이중 반영 방지. `--backfill`만 예외(전체 재구축).

## 8. 격리 원칙

- `objectivity.py`는 `curate.in_date_window`만 import(재사용). 그 반대 방향 의존 없음.
- curate/summarize는 objectivity를 import하지 않는다 → 선별·요약·랭킹 코드 무변경.
- daily 파이프라인(run.sh·daily.yml) 무변경 — 점수 축적은 수동 작업으로 완전 분리.

## 9. 테스트 (`tests/test_objectivity.py`)

- `objectivity_score`: 깨끗한 제목→100 · §6 문구 포함→감점 · 다중 매칭 감점 누적 ·
  "~가 다 했네" 패턴 매칭 · FLOOR 클램프
- EWMA: 정해진 점수 시퀀스 → 기대 이동평균값
- 처음 보는 매체: 그날 평균을 초기값으로
- 멱등성: 같은 날짜 두 번 처리 → 매체 점수·count 불변
- 격리: curate/summarize 소스에 `import objectivity` 없음(정적 확인)

## 10. 완료 조건

- `src/objectivity.py` + `tests/test_objectivity.py`(전건 통과)
- `--backfill`로 기존 raw 처리 → `scores/media.json` 생성, 매체별 점수 분포 확인
- 전용 스킬(`.claude/skills/objectivity-score/`)로 수동 실행·보고·커밋 흐름 동작
- `scores/`가 git 추적되고 커밋으로 누적됨(.gitignore에 scores/ 없음)
- daily 파이프라인 무변경 확인(run.sh·daily.yml diff 없음)
- observe-only 확인: 선별 결과(selected/*.json) 무변화
