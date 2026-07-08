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
  economyCount: number;
  enabledCategories: string[];
}

export const ALL_CATEGORIES = ["경제", "사회", "세계", "IT/테크"];
export const ECONOMY_CATEGORY = "경제";

export const DEFAULT_SETTINGS: DigestSettings = {
  economyCount: 10,
  enabledCategories: [...ALL_CATEGORIES],
};
