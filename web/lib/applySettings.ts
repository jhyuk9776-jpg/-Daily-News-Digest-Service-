import type { Digest, DigestSettings } from "./types";
import { countForCategory, isCategoryEnabled } from "./types";

export function applySettings(digest: Digest, settings: DigestSettings): Digest {
  const cats = digest.categories
    .filter((c) => isCategoryEnabled(settings, c.name))
    .map((c) => ({ ...c, items: c.items.slice(0, countForCategory(settings, c.name)) }));
  return { ...digest, categories: cats };
}
