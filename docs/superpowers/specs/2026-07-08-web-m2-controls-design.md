# 웹 M2 코어 — 경제 개수조절 + 관심분야 필터 (설계)

작성: 2026-07-08 / 이재혁 · Claude
로드맵 위치: M2 "웹 코어" (일정-로드맵 §4b) — 완료 조건 "경제 표시개수 조절 UI(로컬 저장) 동작"

## 1. 목표

기존 정적 다이제스트 조회 화면(PR #4)에 사용자 인터랙션을 추가한다:

- **경제 표시개수 조절** — 기본 10건, 범위 2~10, `localStorage` 저장/복원
- **관심분야 필터** — 경제·사회·세계·IT/테크 4개 분야 on/off (최소 1개는 켜짐)
- **미니멀 읽기 디자인 + 반응형** — 표현 계층을 격리해 추후 카드형으로 저비용 전환 가능

## 2. 핵심 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 상태 구조 | A안: 서버가 JSON 로드 → 클라이언트 셸이 설정·인터랙션 소유 | 정적 로딩(SEO·속도) 유지 + 인터랙션만 클라이언트 격리. Next 15 권장 패턴 |
| 하이드레이션 플래시 | 1번: 기본값으로 SSR 후 mount에서 저장값 교정 | 다이제스트는 위→아래 읽기라 개수 축소가 "아래가 사라지는" 형태로 티가 적음. 무플래시는 폴리시로 미룸 |
| 필터 범위 | 4개 분야 모두 토글, 최소 1개 켜짐 | 경제 미열람 사용자 배려 + 빈 화면 방지 |
| 개수 축소 시 | 파이프라인 선별·정렬 순서의 상위 N건, 웹은 재정렬 안 함 | 선별 로직은 파이프라인 책임(교차검증→매체우선순위→최신순) |
| 디자인 | 미니멀 읽기 우선 + 표현 계층 격리 | M2 완료조건은 "동작"이지 시각 화려함 아님. 카드 전환은 표현 컴포넌트만 교체 |

## 3. 컴포넌트 구조 (상태/표현 분리)

```
app/page.tsx              (서버)  latest.json 로드 → digest를 아래로 전달
 └ components/
    DigestClient.tsx       (클라이언트, "use client")  ← 새 클라이언트 경계
       │  useDigestSettings 훅으로 설정 소유
       │  applySettings(digest, settings) → 표시 데이터 계산 → 아래로 전달
       ├ Controls.tsx       (클라이언트)  상단 바: 분야 토글 4개 + 경제 개수 스텝퍼
       └ DigestView.tsx     (표현, 기존 재사용)  받은 categories 렌더
    
 lib/
    useDigestSettings.ts   설정 상태 + localStorage 저장/복원 (커스텀 훅)
    applySettings.ts       순수 함수: (digest, settings) → 필터·개수 적용된 digest
    types.ts               DigestSettings 추가
```

**책임 분리:**
- `applySettings.ts` — 순수 함수, 부작용/React 무관. 필터·slice 로직. 단위 테스트 핵심.
- `useDigestSettings.ts` — 설정 상태 + localStorage. mount 시 저장값 복원(하이드레이션 1번).
- `Controls.tsx` — 순수 UI. 현재 설정 받고 변경 이벤트만 위로 올림(상태 안 가짐).
- `DigestView.tsx` — 표현 계층. 받은 데이터만 그림. 카드 전환 시 여기만 수정.

전환 국소성: "미니멀↔카드"는 `DigestView`만, "필터 규칙 변경"은 `applySettings`만 건드린다.

## 4. 설정 데이터 + localStorage

**타입** (`lib/types.ts` 추가):
```typescript
interface DigestSettings {
  economyCount: number;          // 2~10, 기본 10
  enabledCategories: string[];   // 켜진 분야명, 기본 ["경제","사회","세계","IT/테크"]
}
```

**localStorage:**
- 키: `"digest-settings"` (단일 키에 JSON 통째로)
- 저장: 설정 변경 시마다 (`useEffect`로 감지 → 직렬화)
- 복원: mount 직후 1회 (`useEffect`로 읽어 상태 교정)

**방어 로직** (`useDigestSettings` 내부):
- 저장값 없음(첫 방문) → 기본값
- JSON 파싱 실패/범위 밖 → 해당 항목만 기본값 보정 (economyCount clamp 2~10, 없는 분야명 무시)
- 최소 1개 분야 제약: 마지막 켜진 분야 끄기 시도 → 무시(`Controls`에서 막고 `applySettings`에서도 폴백 — 이중 안전)

**`applySettings(digest, settings)` 규칙:**
1. `enabledCategories`에 없는 카테고리는 제외
2. 카테고리명이 "경제"면 `items`를 앞에서 `economyCount`개 slice (재정렬 안 함)
3. 나머지 분야는 계약대로 그대로
4. (폴백) 전부 꺼진 상태면 전체 표시

## 5. 에러 처리

| 상황 | 처리 |
|---|---|
| `latest.json` 없음/파싱 실패 | `page.tsx`(서버)에서 발생, 기존 동작 유지(오늘 범위 밖) |
| localStorage 접근 불가(시크릿·비활성) | `try/catch`로 무시 → 메모리 상태로 동작(저장만 안 됨) |
| 저장 설정 JSON 깨짐 | `try/catch` → 기본값 폴백 |
| 범위 밖 값(개수 99·없는 분야) | clamp/무시로 보정 |
| 모든 분야 꺼짐 | `applySettings` 전체 표시 폴백 |

## 6. 테스트 전략 (TDD, vitest)

1. **`applySettings.test.ts`** (핵심):
   - 경제 개수 slice: 10→3, 경계 2·10, 아이템<개수
   - 분야 필터: 특정 분야 꺼짐 → 결과에서 제외
   - 전부 꺼짐 → 전체 폴백
   - 재정렬 안 함(입력 순서 보존)
2. **`useDigestSettings.test.ts`**:
   - 첫 방문 → 기본값
   - 저장→복원 왕복
   - 깨진 JSON → 기본값 폴백
   - 범위 밖 값 clamp
3. **컴포넌트 렌더 테스트** (`DigestClient`/`Controls`):
   - 개수 스텝퍼 조작 → 표시 개수 변함
   - 분야 토글 → 섹션 나타남/사라짐
   - 마지막 분야 끄기 시도 → 막힘

## 7. 오늘 범위 밖 (명시)

- PWA·Vercel 배포·cron→웹 자동 갱신 → 07-09 M3
- 무플래시(useLayoutEffect·초기 숨김) → 폴리시 단계
- 카드형 디자인 → 유료화/폴리시 시점 (표현 계층만 교체)
