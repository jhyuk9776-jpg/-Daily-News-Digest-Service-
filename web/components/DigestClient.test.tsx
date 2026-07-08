import { render, screen, fireEvent } from "@testing-library/react";
import DigestClient from "./DigestClient";
import type { Digest } from "../lib/types";

beforeEach(() => localStorage.clear());

function makeDigest(): Digest {
  const item = (t: string) => ({
    title: t, bullets: ["b"], source: "s", link: `https://x/${t}`, related_links: [],
  });
  return {
    date: "2026-07-08",
    categories: [
      { name: "경제", items: [item("경제A"), item("경제B"), item("경제C")] },
      { name: "사회", items: [item("사회A")] },
    ],
  };
}

test("기본 상태에서 모든 아이템을 렌더한다", () => {
  render(<DigestClient digest={makeDigest()} />);
  expect(screen.getByText("경제A")).toBeDefined();
  expect(screen.getByText("사회A")).toBeDefined();
});

test("경제 개수를 줄이면 아래 아이템이 사라진다", () => {
  render(<DigestClient digest={makeDigest()} />);
  // 10 → 2로 8번 감소(하한 2 clamp) 후 3번째 경제 아이템 사라짐
  const dec = screen.getByLabelText("줄이기");
  for (let i = 0; i < 8; i++) fireEvent.click(dec);
  expect(screen.queryByText("경제C")).toBeNull();
  expect(screen.getByText("경제A")).toBeDefined();
});

test("분야를 끄면 해당 섹션이 사라진다", () => {
  render(<DigestClient digest={makeDigest()} />);
  fireEvent.click(screen.getByLabelText("사회"));
  expect(screen.queryByText("사회A")).toBeNull();
  expect(screen.getByText("경제A")).toBeDefined();
});
