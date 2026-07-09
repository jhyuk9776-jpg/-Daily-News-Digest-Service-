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
  globalCount: number; // 전체 기본 개수 + 개별값 없는 분야의 표시 개수
  counts: Record<string, number>; // 분야명 → 개별 개수(0~10). 없으면 globalCount 사용
}

export const DEFAULT_COUNT = 2;
export const MIN_COUNT = 0; // 0 = 그 분야 숨김
export const MAX_COUNT = 10;

export const DEFAULT_SETTINGS: DigestSettings = {
  globalCount: DEFAULT_COUNT,
  counts: {},
};

// 0~10 드롭다운 옵션.
export const COUNT_OPTIONS = Array.from({ length: MAX_COUNT - MIN_COUNT + 1 }, (_, i) => MIN_COUNT + i);

// 한 분야의 유효 표시 개수: 개별값이 있으면 그것, 없으면 전체값. 0이면 숨김.
export function countForCategory(settings: DigestSettings, name: string): number {
  return settings.counts[name] ?? settings.globalCount;
}
