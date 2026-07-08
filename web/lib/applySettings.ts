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
