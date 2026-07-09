import type { Digest } from "../lib/types";

// 본문(분야별 섹션)만 렌더한다. 제목·컨트롤은 DigestClient가 상단에 배치한다
// (UX 순서: 제목 → 메뉴 → 본문).
export default function DigestView({ digest }: { digest: Digest }) {
  if (digest.categories.length === 0) {
    return <p>표시할 분야가 없습니다. 위에서 개수를 1건 이상으로 설정하세요.</p>;
  }
  return (
    <>
      {digest.categories.map((cat) => (
        <section key={cat.name}>
          <h2>{cat.name}</h2>
          {cat.items.length === 0 ? (
            <p>오늘 수집된 주요 기사가 없습니다.</p>
          ) : (
            cat.items.map((item) => (
              <article key={item.link}>
                <h3>{item.title}</h3>
                <ul>
                  {item.bullets.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
                <p>
                  출처:{" "}
                  <a href={item.link} target="_blank" rel="noreferrer">
                    {item.source}
                  </a>
                  {item.related_links.length > 0
                    ? ` 외 관련 ${item.related_links.length}건`
                    : ""}
                </p>
              </article>
            ))
          )}
        </section>
      ))}
    </>
  );
}
