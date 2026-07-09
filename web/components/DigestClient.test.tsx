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

test("총 표시 건수를 보여준다(경제2+사회2+세계1=5)", () => {
  render(<DigestClient digest={makeDigest()} />);
  expect(screen.getByText("총 5건 표시 중")).toBeDefined();
});

test("분야별 드롭다운 조절은 그 분야에만 적용된다", () => {
  render(<DigestClient digest={makeDigest()} />);
  fireEvent.change(screen.getByLabelText("경제 표시 개수"), { target: { value: "3" } });
  expect(screen.getByText("경제C")).toBeDefined();
  expect(screen.queryByText("사회C")).toBeNull(); // 사회는 그대로 2
});

test("전체 조절은 모든 분야를 통일한다", () => {
  render(<DigestClient digest={makeDigest()} />);
  fireEvent.change(screen.getByLabelText("전체 표시 개수"), { target: { value: "3" } });
  expect(screen.getByText("경제C")).toBeDefined();
  expect(screen.getByText("사회C")).toBeDefined();
});

test("개수 0(숨김)으로 설정하면 그 분야가 사라진다", () => {
  render(<DigestClient digest={makeDigest()} />);
  fireEvent.change(screen.getByLabelText("경제 표시 개수"), { target: { value: "0" } });
  expect(screen.queryByText("경제A")).toBeNull();
  expect(screen.getByText("사회A")).toBeDefined();
});

test("되돌리기는 개수를 기본값으로 되돌린다", () => {
  render(<DigestClient digest={makeDigest()} />);
  fireEvent.change(screen.getByLabelText("경제 표시 개수"), { target: { value: "3" } });
  expect(screen.getByText("경제C")).toBeDefined();
  fireEvent.click(screen.getByText("기본값으로 되돌리기"));
  expect(screen.queryByText("경제C")).toBeNull(); // 다시 2건
});
