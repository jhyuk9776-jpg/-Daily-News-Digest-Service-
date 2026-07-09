"use client";
import { useEffect, useRef, useState } from "react";
import type { DigestSettings } from "./types";
import { DEFAULT_SETTINGS, DEFAULT_COUNT, MIN_COUNT, MAX_COUNT, countForCategory } from "./types";

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
  return { globalCount: clampCount(Number(obj.globalCount)), counts };
}

// 로드된 설정에서 현재 존재하지 않는 분야의 개별값을 버려 stale 키 누적을 막는다.
function reconcile(settings: DigestSettings, categoryNames: string[]): DigestSettings {
  const present = new Set(categoryNames);
  const counts: Record<string, number> = {};
  for (const [k, v] of Object.entries(settings.counts)) {
    if (present.has(k)) counts[k] = v;
  }
  return { ...settings, counts };
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

  // 개별 분야 개수 조절(0 = 숨김)
  const setCount = (name: string, n: number) =>
    setSettings((s) => ({ ...s, counts: { ...s.counts, [name]: clampCount(n) } }));

  // 전체 조절: 모든 개별값을 지우고 전체값으로 통일 → 이후 개별 조절
  const setGlobalCount = (n: number) =>
    setSettings((s) => ({ ...s, globalCount: clampCount(n), counts: {} }));

  // 기본값 되돌리기: 전체값 2·개별값 제거
  const reset = () => setSettings({ globalCount: DEFAULT_COUNT, counts: {} });

  const countOf = (name: string) => countForCategory(settings, name);

  return { settings, countOf, setCount, setGlobalCount, reset };
}
