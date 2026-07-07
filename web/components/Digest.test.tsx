import { render, screen } from "@testing-library/react";
import DigestView from "./Digest";
import type { Digest } from "../lib/types";

const sample: Digest = {
  date: "2026-07-07",
  categories: [
    {
      name: "경제",
      items: [
        {
          title: "테스트 제목",
          bullets: ["첫 번째 사실", "두 번째 사실"],
          source: "한국경제",
          link: "https://example.com/a",
          related_links: [{ source: "매일경제", link: "https://example.com/b" }],
        },
      ],
    },
    { name: "사회", items: [] },
  ],
};

test("제목·불릿·출처·관련건수·빈분야 메시지를 렌더한다", () => {
  render(<DigestView digest={sample} />);
  expect(screen.getByText("테스트 제목")).toBeDefined();
  expect(screen.getByText("첫 번째 사실")).toBeDefined();
  expect(screen.getByText("한국경제")).toBeDefined();
  expect(screen.getByText(/외 관련 1건/)).toBeDefined();
  expect(screen.getByText("오늘 수집된 주요 기사가 없습니다.")).toBeDefined();
});
