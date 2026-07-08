import { renderHook, act } from "@testing-library/react";
import { useDigestSettings, STORAGE_KEY } from "./useDigestSettings";

const CATS = ["경제", "사회", "세계", "IT/테크"];

beforeEach(() => localStorage.clear());

test("첫 방문은 기본값(전체 2, 개별값 없음, 끈 분야 없음)", () => {
  const { result } = renderHook(() => useDigestSettings(CATS));
  expect(result.current.settings.globalCount).toBe(2);
  expect(result.current.settings.counts).toEqual({});
  expect(result.current.settings.disabled).toEqual([]);
  expect(result.current.countOf("세계")).toBe(2); // 개별값 없으면 전체값
});

test("개별 개수는 분야별로 저장되고 1~10으로 clamp된다", () => {
  const { result } = renderHook(() => useDigestSettings(CATS));
  act(() => result.current.setCount("경제", 7));
  expect(result.current.countOf("경제")).toBe(7);
  expect(result.current.countOf("사회")).toBe(2); // 다른 분야는 전체값 유지
  act(() => result.current.setCount("경제", 99));
  expect(result.current.countOf("경제")).toBe(10);
  act(() => result.current.setCount("경제", 0));
  expect(result.current.countOf("경제")).toBe(1);
});

test("전체 조절은 개별값을 지우고 모든 분야를 통일한다", () => {
  const { result } = renderHook(() => useDigestSettings(CATS));
  act(() => result.current.setCount("경제", 7));
  act(() => result.current.setCount("사회", 5));
  act(() => result.current.setGlobalCount(3));
  expect(result.current.settings.counts).toEqual({});
  expect(result.current.countOf("경제")).toBe(3);
  expect(result.current.countOf("사회")).toBe(3);
  expect(result.current.countOf("세계")).toBe(3);
});

test("전체 조절 후 다시 개별 조절이 동작한다", () => {
  const { result } = renderHook(() => useDigestSettings(CATS));
  act(() => result.current.setGlobalCount(3));
  act(() => result.current.setCount("경제", 6));
  expect(result.current.countOf("경제")).toBe(6);
  expect(result.current.countOf("사회")).toBe(3);
});

test("되돌리기는 개수만 초기화하고 끈 분야는 유지한다", () => {
  const { result } = renderHook(() => useDigestSettings(CATS));
  act(() => result.current.setCount("경제", 8));
  act(() => result.current.setGlobalCount(5));
  act(() => result.current.toggleCategory("사회")); // 사회 끔
  act(() => result.current.reset());
  expect(result.current.settings.globalCount).toBe(2);
  expect(result.current.settings.counts).toEqual({});
  expect(result.current.settings.disabled).toEqual(["사회"]); // 필터 상태 유지
});

test("설정 변경이 localStorage에 저장·복원된다", () => {
  const first = renderHook(() => useDigestSettings(CATS));
  act(() => first.result.current.setCount("경제", 4));
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY)!);
  expect(saved.counts["경제"]).toBe(4);
  const second = renderHook(() => useDigestSettings(CATS));
  expect(second.result.current.countOf("경제")).toBe(4);
});

test("깨진 JSON은 기본값으로 폴백한다", () => {
  localStorage.setItem(STORAGE_KEY, "{not json");
  const { result } = renderHook(() => useDigestSettings(CATS));
  expect(result.current.settings.globalCount).toBe(2);
});

test("여러 분야를 순서대로 끌 수 있다", () => {
  const { result } = renderHook(() => useDigestSettings(CATS));
  act(() => result.current.toggleCategory("경제"));
  act(() => result.current.toggleCategory("사회"));
  expect(result.current.isEnabled("경제")).toBe(false);
  expect(result.current.isEnabled("사회")).toBe(false);
  expect(result.current.isEnabled("세계")).toBe(true);
});

test("로드 시 현재 분야에 없는 counts·disabled를 정리한다", () => {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ globalCount: 2, counts: { 경제: 5, 없는분야: 9 }, disabled: ["사회", "없는분야"] })
  );
  const { result } = renderHook(() => useDigestSettings(CATS));
  expect(result.current.settings.counts).toEqual({ 경제: 5 });
  expect(result.current.settings.disabled).toEqual(["사회"]);
});

test("로드 시 모든 분야가 disabled면 필터를 초기화한다", () => {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ globalCount: 2, counts: {}, disabled: [...CATS] })
  );
  const { result } = renderHook(() => useDigestSettings(CATS));
  expect(result.current.settings.disabled).toEqual([]);
});

test("마지막 남은 분야는 끌 수 없다", () => {
  const { result } = renderHook(() => useDigestSettings(CATS));
  act(() => result.current.toggleCategory("경제"));
  act(() => result.current.toggleCategory("사회"));
  act(() => result.current.toggleCategory("세계"));
  act(() => result.current.toggleCategory("IT/테크")); // 마지막 → 무시
  expect(result.current.isEnabled("IT/테크")).toBe(true);
});
