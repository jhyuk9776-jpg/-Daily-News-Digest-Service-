# density 완전 제거 — 선택률로 매체 지표 일원화 (2026-07-22)

## 배경·동기

`feat/selection-redesign` 병합(2026-07-22)으로 선별 tie-break가 **선택률**(`compute_selection_ranks`,
win/appear)로 전환됐다. density(감점 밀도)는 이미 **선별에 미사용**이고, 남은 역할은
브리핑/관찰뿐이다. 매체 객관성 신호를 선택률로 일원화하기로 하고 density를 코드에서
**완전히 제거**한다(매체별 density + 당일 density 둘 다).

핵심 사실:
- density 제거 ≠ 감점 채점 제거. `score_article`/`penalties.yaml`은 낚시 게이트·
  `representative_score`·당일 감점 메모에 쓰이므로 **그대로 둔다**.
- 당일 감점 메모(`총 -Npt` + 표현별 내역)는 `save_article_report`가 매번 새로 계산 →
  density와 무관하게 유지된다.

## 범위

### 제거
1. `objectivity.update_media_scores` — 매체별 density/penalty_points/article_count/
   attribution_total/outlier_total 누적. rank-history를 선택률로 바꾸면 소비처가 사라져
   **함수 통째 삭제**.
2. `objectivity.compute_ranks`(density 기반 순위) — 삭제. 호출부 2곳
   ([objectivity.py:497 run_backfill](../../../src/objectivity.py#L497),
   [objectivity.py:522 main](../../../src/objectivity.py#L522))을 `compute_selection_ranks`로 교체.
3. `save_article_report`의 `density_per_1000` 필드([objectivity.py:431](../../../src/objectivity.py#L431)) — 삭제.
   당일 규모는 `total_points`가 지킨다.
4. `main()` 출력 블록([objectivity.py:524-532](../../../src/objectivity.py#L524)) — density 정렬·컬럼 →
   **선택률 내림차순 정렬**로 재작성(선택률·win/appear 표시).
5. `media.json` — density/attr/outlier 필드가 사라진 구조로 **리셋**(selection_rate는
   어차피 0/0부터 새로 누적. decision-log §1.4 "사전 크게 바꾸면 리셋" 방침과 정합).

### 변경
6. `process_date` — `update_media_scores` 호출 제거. `save_article_report`는 유지하되
   **`processed_dates` 멱등을 process_date가 직접 관리**(update_media_scores가 하던 append를
   이동). 근거: 선택률 멱등은 독립 키 `selection_dates`(update_selection_rates, curate 흐름)라
   무관하고, 당일 리포트 재실행 방지만 process_date에서 지키면 된다.
7. `.claude/skills/daily-briefing` — 점수 섹션 지침에서 density 제거:
   - `밀도 Y/1k` 라인 삭제 → 당일 메모는 `총 -Npt · 표현별 내역`
   - "매체별 density(낮을수록 객관적)" 누적 순위 → **선택률(win/appear, 높을수록 우선)** 순위
   - 인용/이상치 관찰축 문구 정리(매체 누적 attr/outlier 사라짐)

### 유지 (density 아님, 불변)
- `score_article`/`penalties.yaml`, `title_penalty`, `representative_score`
- `save_article_report`(density 필드만 제거), `penalty_memo`, `attribution_count`/outlier(당일 리포트 신선 계산)
- `update_selection_rates`, `compute_selection_ranks`

### 영향
- `run_backfill` — density 재구축 사라짐. 선택률은 raw로 역산 불가(curate 산출물)라 백필은
  **당일 리포트 재생성 + 마지막 날 rank-history(선택률) 갱신**만 남는다. 이미 알려진 제약.
- 테스트:
  - `tests/test_objectivity.py` — density/update_media_scores/compute_ranks 테스트 블록
    (test_new_media_density, test_density_accumulates_across_days, 멱등, test_ranks_by_density_ascending 등) **삭제**.
    process_date 멱등 테스트는 선택률/리포트 기준으로 갱신.
  - `tests/test_representative_backfill.py:1,35` — 낡은 "density" 주석을 "선택률 순위"로 갱신
    (tie-break 로직 자체는 `ranks` 주입이라 동작 불변).
  - `tests/test_body_scoring.py:45`, `tests/test_selection_rate.py:36` — density 언급 주석 정리(로직 영향 확인 후).

## 검증
- `python -m pytest tests/ -q` 그린.
- `python src/objectivity.py 2026-07-22` 실행 → media.json에 density 필드 없음, 선택률 정렬 출력,
  rank-history가 선택률 기반, articles-2026-07-22.json에 density_per_1000 없음.
- 코드 전체에서 `grep -rn density src/` **0건**(주석 포함) — "density 개념 완전 소멸" 확인.
- `python src/curate.py --dry-run` 선별 결과 불변(선별은 density 미사용이었으므로).

## 비목표
- 선택률을 선별에 더 세게 반영(감점/클러스터 순위)하는 것 — 별도 결정(데이터 축적 후).
- 당일 리포트의 attribution/outlier 제거 — density 아니므로 이번 범위 밖.
