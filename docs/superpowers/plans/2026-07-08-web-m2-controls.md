# 웹 M2 코어 (경제 개수조절 + 관심분야 필터) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 정적 다이제스트 조회 화면에 경제 표시개수 조절(2~10, 기본 10)과 관심분야 on/off 필터를 추가하고, 설정을 `localStorage`에 저장·복원한다.

**Architecture:** 서버 컴포넌트(`page.tsx`)가 `latest.json`을 로드해 클라이언트 셸(`DigestClient`)에 넘긴다. 클라이언트가 설정 상태·localStorage·필터/개수 계산을 소유하고, 순수 함수 `applySettings`로 표시 데이터를 계산해 표현 컴포넌트(`DigestView`)에 넘긴다. 상태 로직과 표현을 분리해 추후 카드형 전환을 국소화한다.

**Tech Stack:** Next.js 15 (App Router), React 19, TypeScript, vitest + @testing-library/react (jsdom, globals).

## Global Constraints

- 새 npm 의존성 추가 금지 — 기존 devDependencies(`@testing-library/react` ^16, `vitest` ^2, `jsdom`)만 사용.
- 테스트는 전역 API 사용(`test`/`expect` import 안 함, vitest `globals: true`).
- 작업 디렉터리는 `web/`. 명령은 `web/`에서 실행.
- 경제 카테고리명 문자열은 `"경제"`, 전체 분야명은 `["경제","사회","세계","IT/테크"]`. 실제 `web/public/data/latest.json`의 카테고리명과 정확히 일치함을 Task 1에서 확인.
- 경제 개수 기본 10, 범위 2~10 (clamp). localStorage 키: `"digest-settings"`.
- 최소 1개 분야는 항상 켜져 있어야 함.
- 커밋 메시지 끝에: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 1: 설정 타입 + `applySettings` 순수 함수

**Files:**
- Modify: `web/lib/types.ts` (타입 추가)
- Create: `web/lib/applySettings.ts`
- Test: `web/lib/applySettings.test.ts`

**Interfaces:**
- Consumes: `Digest`, `DigestCategory`, `DigestItem` (기존 `web/lib/types.ts`)
- Produces:
  - `interface DigestSettings { economyCount: number; enabledCategories: string[] }`
  - `const ALL_CATEGORIES: string[]` = `["경제","사회","세계","IT/테크"]`
  - `const ECONOMY_CATEGORY = "경제"`
  - `const DEFAULT_SETTINGS: DigestSettings`
  - `function applySettings(digest: Digest, settings: DigestSettings): Digest`

- [ ] **Step 0: 계약 카테고리명 확인**

Run: `cd web && node -e "const d=require('./public/data/latest.json'); console.log(d.categories.map(c=>c.name))"`
Expected: 출력된 이름들이 `["경제","사회",...]` 형태. `"경제"`가 정확히 포함되는지 확인(불일치 시 상수를 실제 값에 맞춤).

- [ ] **Step 1: 타입·상수 추가 (`web/lib/types.ts` 하단에 추가)**

```typescript
export interface DigestSettings {
  economyCount: number;
  enabledCategories: string[];
}

export const ALL_CATEGORIES = ["경제", "사회", "세계", "IT/테크"];
export const ECONOMY_CATEGORY = "경제";

export const DEFAULT_SETTINGS: DigestSettings = {
  economyCount: 10,
  enabledCategories: [...ALL_CATEGORIES],
};
```

- [ ] **Step 2: 실패 테스트 작성 (`web/lib/applySettings.test.ts`)**

```typescript
import { applySettings } from "./applySettings";
import { DEFAULT_SETTINGS } from "./types";
import type { Digest } from "./types";

function makeDigest(): Digest {
  const item = (t: string) => ({
    title: t, bullets: ["b"], source: "s", link: `https://x/${t}`, related_links: [],
  });
  return {
    date: "2026-07-08",
    categories: [
      { name: "경제", items: [item("e1"), item("e2"), item("e3"), item("e4"), item("e5")] },
      { name: "사회", items: [item("s1"), item("s2")] },
    ],
  };
}

test("경제는 economyCount만큼 앞에서 자른다", () => {
  const out = applySettings(makeDigest(), { ...DEFAULT_SETTINGS, economyCount: 3 });
  const econ = out.categories.find((c) => c.name === "경제")!;
  expect(econ.items.map((i) => i.title)).toEqual(["e1", "e2", "e3"]);
});

test("경제 아이템이 개수보다 적으면 있는 만큼만", () => {
  const out = applySettings(makeDigest(), { ...DEFAULT_SETTINGS, economyCount: 10 });
  const econ = out.categories.find((c) => c.name === "경제")!;
  expect(econ.items).toHaveLength(5);
});

test("경제 외 분야는 자르지 않는다", () => {
  const out = applySettings(makeDigest(), { ...DEFAULT_SETTINGS, economyCount: 2 });
  const soc = out.categories.find((c) => c.name === "사회")!;
  expect(soc.items).toHaveLength(2);
});

test("enabledCategories에 없는 분야는 제외한다", () => {
  const out = applySettings(makeDigest(), { economyCount: 10, enabledCategories: ["경제"] });
  expect(out.categories.map((c) => c.name)).toEqual(["경제"]);
});

test("전부 꺼지면 전체를 표시한다(폴백)", () => {
  const out = applySettings(makeDigest(), { economyCount: 10, enabledCategories: [] });
  expect(out.categories.map((c) => c.name)).toEqual(["경제", "사회"]);
});

test("입력 순서를 재정렬하지 않는다", () => {
  const out = applySettings(makeDigest(), DEFAULT_SETTINGS);
  const econ = out.categories.find((c) => c.name === "경제")!;
  expect(econ.items.map((i) => i.title)).toEqual(["e1", "e2", "e3", "e4", "e5"]);
});
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd web && npx vitest run lib/applySettings.test.ts`
Expected: FAIL — "applySettings is not a function" / 모듈 없음.

- [ ] **Step 4: 구현 (`web/lib/applySettings.ts`)**

```typescript
import type { Digest } from "./types";
import { ECONOMY_CATEGORY } from "./types";
import type { DigestSettings } from "./types";

export function applySettings(digest: Digest, settings: DigestSettings): Digest {
  let cats = digest.categories.filter((c) =>
    settings.enabledCategories.includes(c.name)
  );
  if (cats.length === 0) cats = digest.categories; // 전부 꺼짐 → 전체 폴백
  cats = cats.map((c) =>
    c.name === ECONOMY_CATEGORY
      ? { ...c, items: c.items.slice(0, settings.economyCount) }
      : c
  );
  return { ...digest, categories: cats };
}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd web && npx vitest run lib/applySettings.test.ts`
Expected: PASS (6 passed).

- [ ] **Step 6: 커밋**

```bash
cd web && git add lib/types.ts lib/applySettings.ts lib/applySettings.test.ts
git commit -m "$(printf 'feat(web): applySettings 순수함수 + 설정 타입\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 2: `useDigestSettings` 훅 (상태 + localStorage)

**Files:**
- Create: `web/lib/useDigestSettings.ts`
- Test: `web/lib/useDigestSettings.test.ts`

**Interfaces:**
- Consumes: `DigestSettings`, `DEFAULT_SETTINGS`, `ALL_CATEGORIES` (Task 1)
- Produces:
  - `const STORAGE_KEY = "digest-settings"`
  - `function useDigestSettings(): { settings: DigestSettings; setEconomyCount: (n: number) => void; toggleCategory: (name: string) => void }`
  - clamp 규칙: economyCount 2~10. toggleCategory: 마지막 켜진 분야 끄기 시도는 무시.

- [ ] **Step 1: 실패 테스트 작성 (`web/lib/useDigestSettings.test.ts`)**

```typescript
import { renderHook, act } from "@testing-library/react";
import { useDigestSettings, STORAGE_KEY } from "./useDigestSettings";

beforeEach(() => localStorage.clear());

test("첫 방문은 기본값(경제 10, 4분야)", () => {
  const { result } = renderHook(() => useDigestSettings());
  expect(result.current.settings.economyCount).toBe(10);
  expect(result.current.settings.enabledCategories).toHaveLength(4);
});

test("경제 개수는 2~10으로 clamp된다", () => {
  const { result } = renderHook(() => useDigestSettings());
  act(() => result.current.setEconomyCount(99));
  expect(result.current.settings.economyCount).toBe(10);
  act(() => result.current.setEconomyCount(0));
  expect(result.current.settings.economyCount).toBe(2);
});

test("설정 변경이 localStorage에 저장된다", () => {
  const { result } = renderHook(() => useDigestSettings());
  act(() => result.current.setEconomyCount(3));
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY)!);
  expect(saved.economyCount).toBe(3);
});

test("저장값을 복원한다", () => {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ economyCount: 4, enabledCategories: ["경제", "사회"] })
  );
  const { result } = renderHook(() => useDigestSettings());
  expect(result.current.settings.economyCount).toBe(4);
  expect(result.current.settings.enabledCategories).toEqual(["경제", "사회"]);
});

test("깨진 JSON은 기본값으로 폴백한다", () => {
  localStorage.setItem(STORAGE_KEY, "{not json");
  const { result } = renderHook(() => useDigestSettings());
  expect(result.current.settings.economyCount).toBe(10);
});

test("분야를 토글로 끄고 켤 수 있다", () => {
  const { result } = renderHook(() => useDigestSettings());
  act(() => result.current.toggleCategory("사회"));
  expect(result.current.settings.enabledCategories).not.toContain("사회");
  act(() => result.current.toggleCategory("사회"));
  expect(result.current.settings.enabledCategories).toContain("사회");
});

test("마지막 켜진 분야는 끌 수 없다", () => {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ economyCount: 10, enabledCategories: ["경제"] })
  );
  const { result } = renderHook(() => useDigestSettings());
  act(() => result.current.toggleCategory("경제"));
  expect(result.current.settings.enabledCategories).toEqual(["경제"]);
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npx vitest run lib/useDigestSettings.test.ts`
Expected: FAIL — 모듈/함수 없음.

- [ ] **Step 3: 구현 (`web/lib/useDigestSettings.ts`)**

```typescript
"use client";
import { useEffect, useRef, useState } from "react";
import type { DigestSettings } from "./types";
import { DEFAULT_SETTINGS, ALL_CATEGORIES } from "./types";

export const STORAGE_KEY = "digest-settings";

function clampCount(n: number): number {
  if (Number.isNaN(n)) return DEFAULT_SETTINGS.economyCount;
  return Math.max(2, Math.min(10, Math.round(n)));
}

function sanitize(raw: unknown): DigestSettings {
  const obj = (raw ?? {}) as Partial<DigestSettings>;
  const cats = Array.isArray(obj.enabledCategories)
    ? obj.enabledCategories.filter((c) => ALL_CATEGORIES.includes(c))
    : [];
  return {
    economyCount: clampCount(Number(obj.economyCount)),
    enabledCategories: cats.length > 0 ? cats : [...ALL_CATEGORIES],
  };
}

export function useDigestSettings() {
  const [settings, setSettings] = useState<DigestSettings>(DEFAULT_SETTINGS);
  const firstSave = useRef(true);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setSettings(sanitize(JSON.parse(raw)));
    } catch {
      /* 접근 불가/깨진 값 → 기본값 유지 */
    }
  }, []);

  useEffect(() => {
    if (firstSave.current) {
      firstSave.current = false;
      return;
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      /* 저장 불가(시크릿 모드 등) → 무시 */
    }
  }, [settings]);

  const setEconomyCount = (n: number) =>
    setSettings((s) => ({ ...s, economyCount: clampCount(n) }));

  const toggleCategory = (name: string) =>
    setSettings((s) => {
      const on = s.enabledCategories.includes(name);
      if (on && s.enabledCategories.length === 1) return s; // 마지막 분야 보호
      return {
        ...s,
        enabledCategories: on
          ? s.enabledCategories.filter((c) => c !== name)
          : [...s.enabledCategories, name],
      };
    });

  return { settings, setEconomyCount, toggleCategory };
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npx vitest run lib/useDigestSettings.test.ts`
Expected: PASS (7 passed).

- [ ] **Step 5: 커밋**

```bash
cd web && git add lib/useDigestSettings.ts lib/useDigestSettings.test.ts
git commit -m "$(printf 'feat(web): useDigestSettings 훅 — 상태·localStorage·clamp\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 3: `Controls` UI 컴포넌트

**Files:**
- Create: `web/components/Controls.tsx`
- Test: `web/components/Controls.test.tsx`

**Interfaces:**
- Consumes: `DigestSettings` (Task 1)
- Produces: `Controls` (default export), props:
  `{ settings: DigestSettings; onToggleCategory: (name: string) => void; onEconomyCount: (n: number) => void }`
  - 분야 체크박스 4개(label 텍스트 = 분야명), 경제 개수 `−`/`+` 버튼(aria-label `"줄이기"`/`"늘리기"`)과 현재 값 표시.

- [ ] **Step 1: 실패 테스트 작성 (`web/components/Controls.test.tsx`)**

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import Controls from "./Controls";
import { DEFAULT_SETTINGS } from "../lib/types";

test("4개 분야 체크박스와 경제 개수를 렌더한다", () => {
  render(
    <Controls settings={DEFAULT_SETTINGS} onToggleCategory={() => {}} onEconomyCount={() => {}} />
  );
  expect(screen.getByLabelText("경제")).toBeDefined();
  expect(screen.getByLabelText("IT/테크")).toBeDefined();
  expect(screen.getByText("10")).toBeDefined();
});

test("분야 체크박스 클릭 시 onToggleCategory 호출", () => {
  const spy = vi.fn();
  render(
    <Controls settings={DEFAULT_SETTINGS} onToggleCategory={spy} onEconomyCount={() => {}} />
  );
  fireEvent.click(screen.getByLabelText("사회"));
  expect(spy).toHaveBeenCalledWith("사회");
});

test("+/− 버튼이 현재값 기준으로 onEconomyCount 호출", () => {
  const spy = vi.fn();
  render(
    <Controls
      settings={{ ...DEFAULT_SETTINGS, economyCount: 5 }}
      onToggleCategory={() => {}}
      onEconomyCount={spy}
    />
  );
  fireEvent.click(screen.getByLabelText("늘리기"));
  expect(spy).toHaveBeenCalledWith(6);
  fireEvent.click(screen.getByLabelText("줄이기"));
  expect(spy).toHaveBeenCalledWith(4);
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npx vitest run components/Controls.test.tsx`
Expected: FAIL — 모듈 없음.

- [ ] **Step 3: 구현 (`web/components/Controls.tsx`)**

```tsx
"use client";
import type { DigestSettings } from "../lib/types";
import { ALL_CATEGORIES } from "../lib/types";

export default function Controls({
  settings,
  onToggleCategory,
  onEconomyCount,
}: {
  settings: DigestSettings;
  onToggleCategory: (name: string) => void;
  onEconomyCount: (n: number) => void;
}) {
  return (
    <div className="controls">
      <div className="controls-filters">
        {ALL_CATEGORIES.map((name) => (
          <label key={name} className="filter-chip">
            <input
              type="checkbox"
              checked={settings.enabledCategories.includes(name)}
              onChange={() => onToggleCategory(name)}
            />
            {name}
          </label>
        ))}
      </div>
      <div className="controls-count">
        <span>경제 표시</span>
        <button aria-label="줄이기" onClick={() => onEconomyCount(settings.economyCount - 1)}>
          −
        </button>
        <span className="count-value">{settings.economyCount}</span>
        <button aria-label="늘리기" onClick={() => onEconomyCount(settings.economyCount + 1)}>
          +
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npx vitest run components/Controls.test.tsx`
Expected: PASS (3 passed).

- [ ] **Step 5: 커밋**

```bash
cd web && git add components/Controls.tsx components/Controls.test.tsx
git commit -m "$(printf 'feat(web): Controls — 분야 필터 + 경제 개수 스텝퍼\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 4: `DigestClient` 셸 + `page.tsx` 배선

**Files:**
- Create: `web/components/DigestClient.tsx`
- Test: `web/components/DigestClient.test.tsx`
- Modify: `web/app/page.tsx` (DigestView → DigestClient)

**Interfaces:**
- Consumes: `useDigestSettings` (Task 2), `applySettings` (Task 1), `Controls` (Task 3), `DigestView` (기존 `components/Digest.tsx`), `Digest` 타입
- Produces: `DigestClient` (default export), props `{ digest: Digest }`

- [ ] **Step 1: 실패 테스트 작성 (`web/components/DigestClient.test.tsx`)**

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import DigestClient from "./DigestClient";
import type { Digest } from "../lib/types";

beforeEach(() => localStorage.clear());

function makeDigest(): Digest {
  const item = (t: string) => ({
    title: t, bullets: ["b"], source: "s", link: `https://x/${t}`, related_links: [],
  });
  return {
    date: "2026-07-08",
    categories: [
      { name: "경제", items: [item("경제A"), item("경제B"), item("경제C")] },
      { name: "사회", items: [item("사회A")] },
    ],
  };
}

test("기본 상태에서 모든 아이템을 렌더한다", () => {
  render(<DigestClient digest={makeDigest()} />);
  expect(screen.getByText("경제A")).toBeDefined();
  expect(screen.getByText("사회A")).toBeDefined();
});

test("경제 개수를 줄이면 아래 아이템이 사라진다", () => {
  render(<DigestClient digest={makeDigest()} />);
  // 10 → 2로 8번 감소(하한 2 clamp) 후 3번째 경제 아이템 사라짐
  const dec = screen.getByLabelText("줄이기");
  for (let i = 0; i < 8; i++) fireEvent.click(dec);
  expect(screen.queryByText("경제C")).toBeNull();
  expect(screen.getByText("경제A")).toBeDefined();
});

test("분야를 끄면 해당 섹션이 사라진다", () => {
  render(<DigestClient digest={makeDigest()} />);
  fireEvent.click(screen.getByLabelText("사회"));
  expect(screen.queryByText("사회A")).toBeNull();
  expect(screen.getByText("경제A")).toBeDefined();
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd web && npx vitest run components/DigestClient.test.tsx`
Expected: FAIL — 모듈 없음.

- [ ] **Step 3: 구현 (`web/components/DigestClient.tsx`)**

```tsx
"use client";
import { useDigestSettings } from "../lib/useDigestSettings";
import { applySettings } from "../lib/applySettings";
import Controls from "./Controls";
import DigestView from "./Digest";
import type { Digest } from "../lib/types";

export default function DigestClient({ digest }: { digest: Digest }) {
  const { settings, setEconomyCount, toggleCategory } = useDigestSettings();
  const view = applySettings(digest, settings);
  return (
    <>
      <Controls
        settings={settings}
        onToggleCategory={toggleCategory}
        onEconomyCount={setEconomyCount}
      />
      <DigestView digest={view} />
    </>
  );
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd web && npx vitest run components/DigestClient.test.tsx`
Expected: PASS (3 passed).

- [ ] **Step 5: `page.tsx` 배선 변경 (`web/app/page.tsx`)**

`DigestView` import·사용을 `DigestClient`로 교체:

```tsx
import { promises as fs } from "fs";
import path from "path";
import DigestClient from "../components/DigestClient";
import type { Digest } from "../lib/types";

export default async function Page() {
  const file = path.join(process.cwd(), "public", "data", "latest.json");
  const digest = JSON.parse(await fs.readFile(file, "utf-8")) as Digest;
  return <DigestClient digest={digest} />;
}
```

- [ ] **Step 6: 전체 테스트 + 빌드 확인**

Run: `cd web && npx vitest run && npx next build`
Expected: 모든 테스트 PASS, 빌드 성공(타입 에러 없음).

- [ ] **Step 7: 커밋**

```bash
cd web && git add components/DigestClient.tsx components/DigestClient.test.tsx app/page.tsx
git commit -m "$(printf 'feat(web): DigestClient 셸 배선 — 설정→필터→표시\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 5: 미니멀 읽기 스타일 + 반응형

**Files:**
- Create: `web/app/globals.css`
- Modify: `web/app/layout.tsx` (globals.css import)

**Interfaces:**
- Consumes: Task 3·4가 붙인 className(`controls`, `controls-filters`, `filter-chip`, `controls-count`, `count-value`) + `DigestView`의 시맨틱 태그(`main`,`section`,`h1~h3`,`article`,`ul`).
- Produces: 시각 스타일만. 로직/DOM 구조 변경 없음.

> 이 태스크는 시각 표현이라 자동 테스트 대신 **육안 검증**을 완료 조건으로 한다. `applySettings`/훅 로직은 앞 태스크에서 이미 검증됨.

- [ ] **Step 1: 스타일 작성 (`web/app/globals.css`)**

```css
:root {
  --fg: #1a1a1a;
  --muted: #666;
  --line: #e5e5e5;
  --accent: #1257a8;
  --max: 720px;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--fg);
  font-family: system-ui, -apple-system, "Segoe UI", "Apple SD Gothic Neo", sans-serif;
  line-height: 1.65;
}
main { max-width: var(--max); margin: 0 auto; padding: 1.25rem 1rem 4rem; }
main > h1 { font-size: 1.5rem; margin: 0 0 1rem; }
main > section > h2 {
  font-size: 1.15rem; margin: 2rem 0 0.5rem;
  padding-top: 0.75rem; border-top: 2px solid var(--line);
}
article { margin: 1.25rem 0; }
article h3 { font-size: 1.05rem; margin: 0 0 0.4rem; }
article ul { margin: 0 0 0.4rem; padding-left: 1.2rem; }
article li { margin: 0.15rem 0; }
article p { color: var(--muted); font-size: 0.9rem; margin: 0; }
article a { color: var(--accent); text-decoration: none; }
article a:hover { text-decoration: underline; }

/* 상단 컨트롤 바 */
.controls {
  position: sticky; top: 0; z-index: 10;
  max-width: var(--max); margin: 0 auto;
  display: flex; flex-wrap: wrap; gap: 0.75rem 1rem;
  align-items: center; justify-content: space-between;
  padding: 0.75rem 1rem; background: #fff;
  border-bottom: 1px solid var(--line);
}
.controls-filters { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.filter-chip {
  display: inline-flex; align-items: center; gap: 0.3rem;
  font-size: 0.9rem; padding: 0.2rem 0.5rem;
  border: 1px solid var(--line); border-radius: 999px; cursor: pointer;
}
.controls-count { display: flex; align-items: center; gap: 0.4rem; font-size: 0.9rem; }
.controls-count button {
  width: 1.8rem; height: 1.8rem; font-size: 1.1rem; line-height: 1;
  border: 1px solid var(--line); border-radius: 6px; background: #fafafa; cursor: pointer;
}
.count-value { min-width: 1.2rem; text-align: center; font-variant-numeric: tabular-nums; }

@media (max-width: 480px) {
  .controls { flex-direction: column; align-items: stretch; }
  .controls-count { justify-content: flex-end; }
}
```

- [ ] **Step 2: `layout.tsx`에 import 추가 (`web/app/layout.tsx` 최상단)**

파일 첫 줄에 추가:

```tsx
import "./globals.css";
```

- [ ] **Step 3: 육안 검증**

Run: `cd web && npx next dev`
브라우저로 `http://localhost:3000` 확인:
- 상단 컨트롤 바가 sticky로 고정되고 분야 칩 4개 + 경제 개수 `− N +`가 보인다.
- 개수 `−`/`+`로 경제 아이템 수가 변하고, 새로고침 후에도 유지된다(localStorage).
- 분야 체크 해제 시 해당 섹션이 사라진다.
- 브라우저 폭을 480px 이하로 줄이면 컨트롤이 세로로 쌓인다.
확인 후 dev 서버 종료(Ctrl+C).

- [ ] **Step 4: 커밋**

```bash
cd web && git add app/globals.css app/layout.tsx
git commit -m "$(printf 'feat(web): 미니멀 읽기 스타일 + 반응형 컨트롤 바\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## 완료 조건 (M2)

- 경제 표시개수 조절(2~10, 기본 10)이 동작하고 localStorage에 저장·복원됨.
- 4개 분야 on/off 필터 동작(최소 1개 보호).
- `npx vitest run` 전체 PASS, `npx next build` 성공.
- 미니멀 읽기 스타일 + 480px 반응형 적용.

## 오늘 범위 밖

- PWA·Vercel 배포·cron→웹 자동 갱신 → 07-09 M3
- 무플래시(useLayoutEffect) → 폴리시
- 카드형 디자인 → 표현 계층(`Digest.tsx`)만 교체하는 후속 작업
