---
name: objectivity-score
description: Use when the user asks to accumulate/update media objectivity scores (점수 축적, 객관성 점수 갱신) for this AI 뉴스 프로젝트. Runs the observe-only scorer over collected raw articles and reports media reputation.
---

# 객관성 점수 축적 (수동)

요약하지 않은 수집 기사까지 감점 휴리스틱으로 채점해 매체별 객관성 점수를
이동평균으로 누적한다. observe-only — 선별·랭킹에 반영하지 않는다.
설계: 기획/시스템기획/기능설계/04-객관성-점수축적기.md

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
