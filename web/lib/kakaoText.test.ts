import { buildKakaoText } from "./kakaoText";
import type { Digest } from "./types";

function makeDigest(): Digest {
  return {
    date: "2026-07-08",
    categories: [
      {
        name: "경제",
        items: [
          {
            title: "삼성 사내대출 제한",
            bullets: ["대출 한도 축소", "3분기 시행"],
            source: "한국경제",
            link: "https://www.hankyung.com/article/1",
            related_links: [{ source: "매일경제", link: "https://mk.co.kr/2" }],
          },
        ],
      },
      { name: "세계", items: [] },
    ],
  };
}

test("제목·구분선·불릿·출처(이름만)를 포함한다", () => {
  const text = buildKakaoText(makeDigest());
  expect(text).toContain("오늘의 뉴스 요약 — 2026-07-08");
  expect(text).toContain("──────── 경제 ────────");
  expect(text).toContain("▪ 삼성 사내대출 제한");
  expect(text).toContain("  · 대출 한도 축소");
  expect(text).toContain("출처: 한국경제 외 관련 1건");
});

test("URL·마크다운 링크 문법을 포함하지 않는다", () => {
  const text = buildKakaoText(makeDigest());
  expect(text).not.toContain("http");
  expect(text).not.toContain("](");
});

test("기사 없는 분야는 안내 문구를 넣는다", () => {
  const text = buildKakaoText(makeDigest());
  expect(text).toContain("──────── 세계 ────────");
  expect(text).toContain("오늘 수집된 주요 기사가 없습니다.");
});
