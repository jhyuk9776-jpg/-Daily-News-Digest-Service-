# Day 4 설계 — AI 요약 / 마크다운 생성

작성일: 2026-06-30
대상: 로드맵 Day 4 "AI 요약/마크다운 생성 (날짜별 다이제스트 파일 생성)"

## 1. 목표

`selected/YYYY-MM-DD.json`(Day 3 선별 결과)을 입력으로, 분야별 기사를 사실 중심으로
요약해 최종 결과물 `News/YYYY-MM-DD.md`를 만든다. 파이프라인의 마지막 단계.

근거: `AI_CONTEXT.md` §6(요약 원칙), `기획/02-mvp-spec.md`(결과물 형식),
`기획/04-decision-log.md` "1.2 Day 4 요약 단계 결정".

## 2. 결정 사항 (04-decision-log 1.2)

| 항목 | 결정 |
|---|---|
| AI 모델 | Claude Haiku 4.5 (Replicate 모델 `anthropic/claude-4.5-haiku`) |
| SDK | `replicate` Python SDK, `replicate.run` (Anthropic 콘솔 결제 불가로 Replicate 공식 채널 사용) |
| API 키 | `.env`의 `REPLICATE_API_TOKEN` (`.gitignore` 처리) |
| 제약 | `max_tokens` 최소 1024 · 잔액 $5 미만 시 분당 6건 제한 → 429 자동 재시도 |
| 본문 추출 | 빈/짧은 요약만 보강(BeautifulSoup), 대상은 최종 8건뿐 |
| 폴백 체인 | 같은 사건(클러스터) 내 다음 우선순위 매체로 순차 재시도, 전부 실패 시 "추출 실패로 제외" |
| 요약 호출 | 기사별 개별 호출(격리성·출처 1:1·캐시) |
| 출처 표기 | 사실 단위로 출처 링크 부착, "출처 없는 사실은 싣지 않는다" |

## 3. 파일 구조

```
src/
  extract.py        # 본문 추출 + 클러스터 폴백 체인
  summarize.py      # Day 4 진입점: 요약 + 마크다운 생성
.env / .env.example # ANTHROPIC_API_KEY (.env는 gitignore)
cache/summaries.json # URL→요약 캐시 (gitignore)
News/YYYY-MM-DD.md  # 최종 결과물 (커밋)
```

## 4. 동작 흐름 (선별된 8건 각각)

1. **내용 확보**(`extract.get_content`): RSS 요약이 40자 이상이면 그대로, 아니면 대표
   매체 본문 추출 → 실패 시 클러스터 내 다음 매체 본문 → 전부 실패 시 제외 표시
2. **캐시 확인**: URL이 `cache/summaries.json`에 있으면 API 건너뜀
3. **Haiku 요약**: 시스템 프롬프트에 AI_CONTEXT §6 규칙 고정, 사실 1~3개를 불릿으로
4. **예외 처리**: SDK 자동 재시도 후에도 실패하면 "요약 생성 실패 — 원문 링크만"
5. **마크다운 조립**: 분야 → 제목 → 사실 불릿 → 출처 링크(+관련 N건). 빈 분야는
   "오늘 수집된 주요 기사가 없습니다", 추출 실패는 안내 문구

## 5. 안전장치

- `--dry-run`: API 호출 없이 흐름·추출만 검증(비용 0)
- 같은 날짜 `.md` 존재 시 덮어쓰기(Phase 1 정책)
- API 키 없으면 명확한 오류로 중단

## 6. 결과물 형식 (02-mvp-spec 준수)

```markdown
# 데일리 뉴스 다이제스트 - 2026-06-30

> 생성: ... · 요약 실패 0건 · 추출 실패 0건

## 경제

### {기사 제목}
- {사실 요약}
- 출처: [매체](링크) 외 관련 N건
```

## 7. 완료 기준

`python3 src/summarize.py --dry-run` 으로 8건 흐름과 `News/<오늘>.md` 생성 확인(완료).
실제 요약은 `.env`에 키 설정 후 `python3 src/summarize.py` 실행.
