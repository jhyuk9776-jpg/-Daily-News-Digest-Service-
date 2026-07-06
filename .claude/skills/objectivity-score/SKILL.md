---
name: objectivity-score
description: Use when the user asks to accumulate/update media objectivity scores (점수 축적, 객관성 점수 갱신) for this AI 뉴스 프로젝트, or as the scoring step of the daily briefing. Runs the observe-only scorer over collected raw articles and reports the day's penalty memo + accumulated media reputation.
---

# 객관성 점수 축적 (수동 / 브리핑에서 호출)

수집한 기사(요약 대상 8건이 아니라 **전량**)의 제목·RSS요약을 감점 사전으로 채점해
매체별 **감점 밀도(1000건당 감점 point, 낮을수록 객관적)**를 누적한다. observe-only — 선별·랭킹에 반영하지 않는다.

- 감점 기준(사전): **`penalties.yaml`**(루트). 코드가 직접 읽는다. 없으면 시드로 폴백.
- 채점 로직: `src/objectivity.py`. 설계: `기획/시스템기획/기능설계/04-객관성-점수축적기.md`.
- 저장(A안): `scores/media.json`(누적) + `scores/articles-<날짜>.json`(당일 감점분 + penalty_memo).
- 트랙2(본문 감사): `scores/digest-audit-<날짜>.json`. 실행: `python3 src/digest_audit.py <날짜>`.

> **매일 채점은 cron이 자동으로 한다**(`.github/workflows/daily.yml`가 요약 직후 `objectivity.py` 실행 →
> `scores/` 커밋). 그래서 아침 브리핑은 커밋된 `scores/`를 **읽기만** 한다. 이 스킬은
> **수동 재실행·리셋·백필·검수**용이다. raw는 보관하지 않으므로(과거 재채점 불가) 과거 날짜 채점은 그 raw가
> 로컬에 있을 때만 가능하다.

## 언제
- 사용자가 "점수 축적해줘", "객관성 점수 갱신", "매체 점수 돌려줘"라고 할 때(수동 재실행·검수).
- 감점 사전(`penalties.yaml`)을 크게 바꾼 뒤 누적을 **리셋**하고 싶을 때(`media.json` 삭제 후 새로 시작).
- 로컬에 raw가 있는 날을 백필하거나 오탐을 점검할 때.

## 절차

1. **날짜·raw 확인.** 기본은 오늘(KST). `raw/<날짜>.json`이 없으면 **먼저 수집**한다:
   `TZ=Asia/Seoul python3 src/fetch.py` (오늘 기준). 과거 날짜의 raw가 없으면 채점 불가 —
   그 사실을 알리고 건너뛴다(RSS는 지나간 날짜를 안정적으로 주지 않는다).
   ⚠️ cron이 만든 raw는 runner에서 소멸하므로, 그날 로컬에서 안 돌렸으면 raw가 없다.
2. **채점·누적 실행:**
   - 오늘: `TZ=Asia/Seoul python3 src/objectivity.py`
   - 특정 날짜: `python3 src/objectivity.py YYYY-MM-DD` (해당 raw 필요)
   - 전체 재구축(사전 바꾼 뒤 소급): `python3 src/objectivity.py --backfill`
   - 본문 감사(트랙2, 선택): `python3 src/digest_audit.py YYYY-MM-DD`
3. **결과 보고 — 두 가지를 같이 낸다:**
   - **당일 감점 메모**(`articles-<날짜>.json`): `total_points`(총감점) · `density_per_1000`(1000건당 감점밀도) ·
     `penalty_memo.by_expr`(표현별 횟수·감점) · `penalty_memo.by_source`(매체별 감점).
     "무엇이·왜·얼마나 깎였는지"를 사람이 읽게 정리한다.
   - **누적 표**(`media.json`): 매체별 `density_per_1000`(감점밀도, **낮을수록 객관적**) 오름차순 정렬.
     컬럼: 매체 · 감점밀도(/1k) · 표본(`article_count`) · 인용(`attribution_total`) · 이상치(`outlier_total`).
   - **트랙2 감사**(`digest-audit-<날짜>.json`이 있을 때만): "본문 감사: 감사 N건, 감점 M건" 요약 추가.
4. **오탐 점검.** 당일 감점 표현 중 사실 기사를 잘못 깎은 게 있는지 본다. 있으면
   `penalties.yaml` 조정 후보로 메모(가중치↓ 또는 `observe_candidates`로 강등).
5. **커밋(확인 후).** `git add scores/ && git commit -m "chore: 객관성 점수 축적 <날짜>"`.

## 주의
- observe-only: curate/summarize/run.sh/daily.yml을 건드리지 않는다.
- 멱등: 같은 날짜를 다시 돌려도 누적에 이중 반영되지 않는다(--backfill만 전체 재구축).
- 감점 기준은 **`penalties.yaml`에서 편집**한다(코드 수정 아님). 등급 weight(strong15/medium8/weak3),
  `observe_candidates`(감점 0·기록만), `exclusions`(단독 모호어 금지) 구조.
- 시간에 따라 RSS가 달라지므로, 같은 날짜라도 수집 시점에 따라 표본이 조금 다를 수 있다(observe-only라 허용).
- 기사별 내부 score(100-감점 방식)는 참고용이며, **매체 누적 지표는 density_per_1000**(밀도)을 기준으로 판단한다.
