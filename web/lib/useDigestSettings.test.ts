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
