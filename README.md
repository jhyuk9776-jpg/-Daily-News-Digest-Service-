# 데일리 뉴스 다이제스트

매일 아침, 신뢰할 수 있는 뉴스 출처에서 주요 사건을 수집하고 중복을 줄인 뒤,
판단·해석을 덜어낸 **사실 중심 요약**으로 정리하는 데일리 뉴스 다이제스트.

결과물: `News/YYYY-MM-DD.md` (분야별 2건, 하루 총 8건 · 출처 링크 1:1 부착)

프로젝트 배경·원칙은 [`AI_CONTEXT.md`](AI_CONTEXT.md), 결정 기록은
[`기획/04-decision-log.md`](기획/04-decision-log.md) 참고.

## 파이프라인 구조

```
sources.yaml
   │  RSS 출처(분야별, 우선순위)
   ▼
src/fetch.py      수집     → raw/YYYY-MM-DD.json      (전체 기사)
   ▼
src/curate.py     선별     → selected/YYYY-MM-DD.json (증거점수·중복제거·분야별 2건)
   ▼
src/summarize.py  요약     → News/YYYY-MM-DD.md       (Claude Haiku 4.5, 사실 불릿)
  └ src/extract.py 로 본문 확보(짧은 RSS는 본문 추출, 실패 시 다음 순위 매체로 폴백)
```

## 준비 (최초 1회)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.env` 파일에 요약 API 토큰을 넣는다(커밋 금지, `.gitignore`에 포함됨):

```
REPLICATE_API_TOKEN=여기에_토큰
```

> 요약은 Replicate 경유 Claude Haiku 4.5(`anthropic/claude-4.5-haiku`)를 쓴다.
> 이유·제약은 결정 로그 1.2 참고.

## 실행

```bash
./run.sh
```

수집 → 선별 → 요약을 순서대로 돌리고 `News/오늘.md`를 생성한다.
개별 단계만 돌리려면:

```bash
python3 src/fetch.py                 # 수집
python3 src/curate.py [YYYY-MM-DD]   # 선별 (기본: 오늘)
python3 src/summarize.py [YYYY-MM-DD]# 요약 (--dry-run 시 API 미호출)
```

## 테스트

```bash
python3 -m unittest discover -s tests
```

## 자동 실행 (GitHub Actions)

[`.github/workflows/daily.yml`](.github/workflows/daily.yml)이 매일 아침 파이프라인을
실행하고 생성된 `News/YYYY-MM-DD.md`를 `main`에 자동 커밋한다.

활성화하려면:

1. GitHub 저장소 → **Settings → Secrets and variables → Actions** 에
   `REPLICATE_API_TOKEN` 시크릿을 추가한다.
2. 워크플로 파일을 커밋·푸시한다.
3. 실행 시각은 `daily.yml`의 `cron` 값으로 조정한다(UTC 기준).
