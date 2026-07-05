# Day 2 설계 — RSS 수집 모듈

작성일: 2026-06-30
대상: 로드맵 Day 2 "수집 기능 구현 (고정 소스에서 기사 리스트 수집)"

## 1. 목표

고정된 국내 종합지 RSS 출처에서 4개 분야(경제·사회·세계·IT/테크)의 기사 리스트를
수집해 날짜별 raw JSON으로 저장한다. **선별·날짜필터·중복제거는 Day 3, 요약은 Day 4**이며
이 단계에서는 하지 않는다.

근거 문서:
- `AI_CONTEXT.md` (Phase 1 범위, 요약/제품 원칙)
- `기획/03-system-architecture.md` (파이프라인, 예외 처리 원칙)
- `기획/decision-log.md` (분야 4종, 분야별 2~3개 출처, 백엔드 Python 유지)

## 2. 결정 사항

| 항목 | 결정 |
|---|---|
| 언어 | Python (Phase 1 백엔드 파이프라인). TypeScript는 Phase 3 프론트 전용 |
| 저장 포맷 | JSON (언어 중립, Day 3 입력 및 향후 TS 프론트 호환) |
| 출처 구성 | 국내 종합지/경제지/IT지 RSS 중심 |
| 분류 방식 | **방식 A** — 출처를 분야 칸에 배치. 기사 분야 = 그 기사를 가져온 피드의 분야. AI/키워드 자동분류 안 함 |
| 멀티 분야 매체 | 같은 매체라도 분야별 RSS 주소가 다르면 각 분야에 별도 줄로 추가 |

## 3. 파일 구조

```
News/
  sources.yaml          # RSS 출처 주소록 (분야별 매핑)
  src/
    fetch.py            # 수집 모듈 (실행 진입점)
  raw/
    YYYY-MM-DD.json     # 수집 결과 (Day 3 입력)
  requirements.txt      # feedparser, requests, pyyaml
```

## 4. sources.yaml 구조

```yaml
경제:
  - 매체명: 한국경제
    url: https://www.hankyung.com/feed/economy
    우선순위: 1
사회:
  - 매체명: 한겨레
    url: https://www.hani.co.kr/rss/society/
    우선순위: 1
세계: [...]
IT/테크: [...]
```

- 분야별 2~3개. 우선순위는 Day 3 중복제거에서 사용 예정(이번엔 기록만).

## 5. fetch.py 동작

1. `sources.yaml` 로드
2. 각 피드를 `feedparser`로 파싱
3. 기사별 필드 추출: `title, link, published, summary, source(매체명), category(분야), fetched_at`
4. 분야별 수집 건수를 터미널에 출력
5. 전체 결과 + 실패 소스 목록을 `raw/YYYY-MM-DD.json`에 저장

이 단계에서 하지 않는 것: 날짜 필터, 분야별 2건 추리기, 중복 제거, 요약.

## 6. 예외 처리 (아키텍처 원칙 준수)

- 한 소스 실패 → 경고 출력 후 계속 진행, 실패 목록에 기록
- 모든 소스 실패 → JSON 생성 중단 + 명확한 오류 출력
- 같은 날짜 파일 존재 시 → 덮어쓰기 (Phase 1 단순 정책)

## 7. 출력 JSON 형식

```json
{
  "date": "2026-06-30",
  "fetched_at": "2026-06-30T09:00:00",
  "counts": { "경제": 12, "사회": 9, "세계": 7, "IT/테크": 8 },
  "failed_sources": [],
  "articles": [
    {
      "title": "...",
      "link": "https://...",
      "published": "...",
      "summary": "...",
      "source": "한국경제",
      "category": "경제",
      "fetched_at": "2026-06-30T09:00:00"
    }
  ]
}
```

## 8. 검증

구현 후 실제 실행해 살아있는 피드를 확인하고, 죽은/불안정 피드는 교체한다.
완료 기준: `python3 src/fetch.py` 실행 시 분야별 건수가 출력되고 `raw/<오늘>.json`이 생성된다.
```
