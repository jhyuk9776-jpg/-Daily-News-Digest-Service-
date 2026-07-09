import type { Digest, DigestSettings } from "./types";
import { countForCategory } from "./types";

// 설정을 적용해 표시용 다이제스트를 만든다.
// - 개수 0인 분야는 숨긴다(제외).
// - 개수 > 0이면 앞에서 그만큼 자른다(데이터가 부족하면 있는 만큼).
//   데이터가 0건이어도 분야는 남겨 "수집된 기사 없음" 안내가 보이게 한다.
export function applySettings(digest: Digest, settings: DigestSettings): Digest {
  const cats = digest.categories
    .filter((c) => countForCategory(settings, c.name) > 0)
    .map((c) => ({ ...c, items: c.items.slice(0, countForCategory(settings, c.name)) }));
  return { ...digest, categories: cats };
}

// 현재 설정으로 실제 표시되는 총 기사 수(구독 등급별 상한 인지용).
export function totalShown(digest: Digest, settings: DigestSettings): number {
  return digest.categories.reduce(
    (n, c) => n + Math.min(Math.max(0, countForCategory(settings, c.name)), c.items.length),
    0
  );
}
