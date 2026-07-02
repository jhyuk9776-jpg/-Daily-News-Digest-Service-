"""파이프라인 실패 로그 축적 (요약 실패·본문추출 실패·호출 예외).

실패·에러 데이터는 추출기 개선·엣지케이스 사전의 연료다. 실패 0건이면 파일을
만들지 않는다. failures/는 git 추적해 커밋으로 누적한다(scores/ 선례).

설계: 기획/시스템기획/기능설계/06-실패처리.md
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURES_DIR = ROOT / "failures"
KST = timezone(timedelta(hours=9))


def save_failure_log(date: str, total_articles: int, failures: list):
    """실패 목록을 failures/failures-<date>.json에 기록한다.

    실패 0건이면 아무것도 만들지 않고 None을 반환한다.
    """
    if not failures:
        return None
    FAILURES_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": date,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "total_articles": total_articles,
        "failed_count": len(failures),
        "failures": failures,
    }
    path = FAILURES_DIR / f"failures-{date}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path
