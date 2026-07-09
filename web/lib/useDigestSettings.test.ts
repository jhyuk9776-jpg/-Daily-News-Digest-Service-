import { renderHook, act } from "@testing-library/react";
import { useDigestSettings, STORAGE_KEY } from "./useDigestSettings";

const CATS = ["경제", "사회", "세계", "IT/테크"];

beforeEach(() => localStorage.clear());

test("첫 방문은 기본값(전체 2, 개별값 없음)", () => {
  const { result } = renderHook(() => useDigestSettings(CATS));
  expect(result.current.settings.globalCount).toBe(2);
  expect(result.current.settings.counts).toEqual({});
  expect(result.current.countOf("세계")).toBe(2); // 개별값 없으면 전체값
});

test("개별 개수는 분야별로 저장되고 0~10으로 clamp된다", () => {
  const { result } = renderHook(() => useDigestSettings(CATS));
  act(() => result.current.setCount("경제", 7));
  expect(result.current.countOf("경제")).toBe(7);
  expect(result.current.countOf("사회")).toBe(2); // 다른 분야는 전체값 유지
  act(() => result.current.setCount("경제", 99));
  expect(result.current.countOf("경제")).toBe(10);
  act(() => result.current.setCount("경제", 0));
  expect(result.current.countOf("경제")).toBe(0); // 0 = 숨김 허용
  act(() => result.current.setCount("경제", -3));
  expect(result.current.countOf("경제")).toBe(0); // 음수는 0으로 clamp
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

test("되돌리기는 전체값 2·개별값 제거로 초기화한다", () => {
  const { result } = renderHook(() => useDigestSettings(CATS));
  act(() => result.current.setCount("경제", 8));
  act(() => result.current.setGlobalCount(5));
  act(() => result.current.reset());
  expect(result.current.settings.globalCount).toBe(2);
  expect(result.current.settings.counts).toEqual({});
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

test("로드 시 현재 분야에 없는 counts를 정리한다", () => {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ globalCount: 2, counts: { 경제: 5, 없는분야: 9 } })
  );
  const { result } = renderHook(() => useDigestSettings(CATS));
  expect(result.current.settings.counts).toEqual({ 경제: 5 });
});
