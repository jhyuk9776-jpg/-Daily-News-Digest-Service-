#!/usr/bin/env bash
# 데일리 뉴스 다이제스트 파이프라인 전체 실행 (수집 → 선별 → 요약/마크다운).
#
# 세 스크립트 모두 "오늘(KST)"을 기준으로 동작하도록 TZ를 고정한다.
# (GitHub Actions 등 UTC 환경에서 날짜가 어긋나 raw/selected/News 파일이
#  서로 다른 날짜로 저장되는 것을 막는다.)
#
# 사용법:
#   ./run.sh        # 오늘(KST) 다이제스트 생성
set -euo pipefail

cd "$(dirname "$0")"
export TZ="Asia/Seoul"

DATE="$(date +%F)"
echo "▶ 파이프라인 시작: ${DATE} (KST)"

echo "· 1/3 수집(fetch)"
python3 src/fetch.py

echo "· 2/3 선별/중복제거(curate)"
python3 src/curate.py

echo "· 3/3 요약/마크다운(summarize)"
python3 src/summarize.py

echo "✅ 완료: News/${DATE}.md"
