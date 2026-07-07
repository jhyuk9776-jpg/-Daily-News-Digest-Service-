import type { Digest } from "../lib/types";

export default function DigestView({ digest }: { digest: Digest }) {
  return (
    <main>
      <h1>오늘의 뉴스 요약 — {digest.date}</h1>
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
    </main>
  );
}
