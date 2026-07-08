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
