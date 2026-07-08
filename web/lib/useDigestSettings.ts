"use client";
import { useEffect, useRef, useState } from "react";
import type { DigestSettings } from "./types";
import {
  DEFAULT_SETTINGS,
  DEFAULT_COUNT,
  MIN_COUNT,
  MAX_COUNT,
  countForCategory,
  isCategoryEnabled,
} from "./types";

export const STORAGE_KEY = "digest-settings";

function clampCount(n: number): number {
  if (Number.isNaN(n)) return DEFAULT_COUNT;
  return Math.max(MIN_COUNT, Math.min(MAX_COUNT, Math.round(n)));
}

function sanitize(raw: unknown): DigestSettings {
  const obj =
    typeof raw === "object" && raw !== null ? (raw as Partial<DigestSettings>) : {};
  const counts: Record<string, number> = {};
  if (obj.counts && typeof obj.counts === "object") {
    for (const [k, v] of Object.entries(obj.counts)) counts[k] = clampCount(Number(v));
  }
  const disabled = Array.isArray(obj.disabled)
    ? obj.disabled.filter((c): c is string => typeof c === "string")
    : [];
  return { globalCount: clampCount(Number(obj.globalCount)), counts, disabled };
}

// 로드된 설정을 현재 실제 분야에 맞춰 정리한다:
// - 없는 분야의 개별값/필터는 버려 stale 키 누적을 막고
// - 모든 분야가 꺼진 상태면 필터를 초기화해 빈 화면을 방지한다(최소 1개 표시).
function reconcile(settings: DigestSettings, categoryNames: string[]): DigestSettings {
  const present = new Set(categoryNames);
  const counts: Record<string, number> = {};
  for (const [k, v] of Object.entries(settings.counts)) {
    if (present.has(k)) counts[k] = v;
  }
  let disabled = settings.disabled.filter((c) => present.has(c));
  if (categoryNames.length > 0 && disabled.length >= categoryNames.length) {
    disabled = [];
  }
  return { ...settings, counts, disabled };
}

export function useDigestSettings(categoryNames: string[]) {
  const [settings, setSettings] = useState<DigestSettings>(DEFAULT_SETTINGS);
  const firstSave = useRef(true);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setSettings(reconcile(sanitize(JSON.parse(raw)), categoryNames));
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

  // 개별 분야 개수 조절
  const setCount = (name: string, n: number) =>
    setSettings((s) => ({ ...s, counts: { ...s.counts, [name]: clampCount(n) } }));

  // 전체 조절: 모든 개별값을 지우고 전체값으로 통일 → 이후 개별 조절
  const setGlobalCount = (n: number) =>
    setSettings((s) => ({ ...s, globalCount: clampCount(n), counts: {} }));

  // 기본값 되돌리기: 개수만 초기화(전체값 2·개별값 제거), 켜짐/꺼짐 상태는 유지
  const reset = () =>
    setSettings((s) => ({ ...s, globalCount: DEFAULT_COUNT, counts: {} }));

  const toggleCategory = (name: string) =>
    setSettings((s) => {
      if (s.disabled.includes(name)) {
        return { ...s, disabled: s.disabled.filter((c) => c !== name) };
      }
      const enabledPresent = categoryNames.filter((c) => !s.disabled.includes(c));
      if (enabledPresent.length <= 1) return s; // 마지막 남은 분야 보호
      return { ...s, disabled: [...s.disabled, name] };
    });

  const countOf = (name: string) => countForCategory(settings, name);
  const isEnabled = (name: string) => isCategoryEnabled(settings, name);

  return {
    settings,
    countOf,
    isEnabled,
    setCount,
    setGlobalCount,
    toggleCategory,
    reset,
  };
}
