export interface RelatedLink {
  source: string;
  link: string;
}

export interface DigestItem {
  title: string;
  bullets: string[];
  source: string;
  link: string;
  related_links: RelatedLink[];
}

export interface DigestCategory {
  name: string;
  items: DigestItem[];
}

export interface Digest {
  date: string;
  categories: DigestCategory[];
}

export interface DigestSettings {
  globalCount: number; // 전체 스텝퍼 값 + 개별값 없는 분야의 기본 개수
  counts: Record<string, number>; // 분야명 → 개별 개수 (없으면 globalCount 사용)
  disabled: string[]; // 꺼진 분야명
}

export const DEFAULT_COUNT = 2;
export const MIN_COUNT = 1;
export const MAX_COUNT = 10;

export const DEFAULT_SETTINGS: DigestSettings = {
  globalCount: DEFAULT_COUNT,
  counts: {},
  disabled: [],
};

// 한 분야의 유효 표시 개수: 개별값이 있으면 그것, 없으면 전체값.
export function countForCategory(settings: DigestSettings, name: string): number {
  return settings.counts[name] ?? settings.globalCount;
}

export function isCategoryEnabled(settings: DigestSettings, name: string): boolean {
  return !settings.disabled.includes(name);
}
