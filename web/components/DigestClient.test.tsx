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
      { name: "사회", items: [item("사회A"), item("사회B"), item("사회C")] },
      { name: "세계", items: [item("세계A")] },
    ],
  };
}

test("기본값(전체 2)으로 각 분야 앞 2건만 렌더한다", () => {
  render(<DigestClient digest={makeDigest()} />);
  expect(screen.getByText("경제A")).toBeDefined();
  expect(screen.getByText("경제B")).toBeDefined();
  expect(screen.queryByText("경제C")).toBeNull();
  expect(screen.queryByText("사회C")).toBeNull();
  expect(screen.getByText("세계A")).toBeDefined();
});

test("분야별 개수 조절은 그 분야에만 적용된다", () => {
  render(<DigestClient digest={makeDigest()} />);
  fireEvent.click(screen.getByLabelText("경제 늘리기")); // 경제 2 → 3
  expect(screen.getByText("경제C")).toBeDefined();
  expect(screen.queryByText("사회C")).toBeNull(); // 사회는 그대로 2
});

test("전체 조절은 모든 분야를 통일한다", () => {
  render(<DigestClient digest={makeDigest()} />);
  fireEvent.click(screen.getByLabelText("전체 늘리기")); // 전체 2 → 3
  expect(screen.getByText("경제C")).toBeDefined();
  expect(screen.getByText("사회C")).toBeDefined();
});

test("여러 분야를 순서대로 끄면 모두 사라진다", () => {
  render(<DigestClient digest={makeDigest()} />);
  fireEvent.click(screen.getByLabelText("경제"));
  fireEvent.click(screen.getByLabelText("사회"));
  expect(screen.queryByText("경제A")).toBeNull();
  expect(screen.queryByText("사회A")).toBeNull();
  expect(screen.getByText("세계A")).toBeDefined();
});

test("되돌리기는 개수를 기본값으로 되돌린다", () => {
  render(<DigestClient digest={makeDigest()} />);
  fireEvent.click(screen.getByLabelText("경제 늘리기")); // 경제 3
  expect(screen.getByText("경제C")).toBeDefined();
  fireEvent.click(screen.getByText("기본값으로 되돌리기"));
  expect(screen.queryByText("경제C")).toBeNull(); // 다시 2건
});
