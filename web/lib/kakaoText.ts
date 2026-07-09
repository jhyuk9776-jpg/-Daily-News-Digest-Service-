import type { Digest } from "./types";

// 현재 화면의 다이제스트를 카카오톡 복붙용 plain 텍스트로 만든다.
// 서식 없는 텍스트라 유니코드 기호(▪ · ────)를 쓰고, 출처는 이름만(링크 제외).
// notify.py의 _render_text와 같은 포맷을 웹에서 재현한 것.
export function buildKakaoText(digest: Digest): string {
  const lines: string[] = [`오늘의 뉴스 요약 — ${digest.date}`, ""];
  for (const cat of digest.categories) {
    lines.push(`──────── ${cat.name} ────────`);
    if (cat.items.length === 0) {
      lines.push("오늘 수집된 주요 기사가 없습니다.", "");
      continue;
    }
    for (const item of cat.items) {
      lines.push(`▪ ${item.title}`);
      for (const b of item.bullets) lines.push(`  · ${b}`);
      const extra =
        item.related_links.length > 0 ? ` 외 관련 ${item.related_links.length}건` : "";
      lines.push(`  출처: ${item.source}${extra}`);
      lines.push("");
    }
  }
  return lines.join("\n").trim() + "\n";
}
