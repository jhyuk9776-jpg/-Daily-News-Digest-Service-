import { applySettings } from "./applySettings";
import { DEFAULT_SETTINGS } from "./types";
import type { Digest } from "./types";

function makeDigest(): Digest {
  const item = (t: string) => ({
    title: t, bullets: ["b"], source: "s", link: `https://x/${t}`, related_links: [],
  });
  return {
    date: "2026-07-08",
    categories: [
      { name: "경제", items: [item("e1"), item("e2"), item("e3"), item("e4"), item("e5")] },
      { name: "사회", items: [item("s1"), item("s2"), item("s3")] },
    ],
  };
}

test("개별값이 없으면 globalCount만큼 모든 분야를 자른다", () => {
  const out = applySettings(makeDigest(), { globalCount: 2, counts: {}, disabled: [] });
  const econ = out.categories.find((c) => c.name === "경제")!;
  const soc = out.categories.find((c) => c.name === "사회")!;
  expect(econ.items.map((i) => i.title)).toEqual(["e1", "e2"]);
  expect(soc.items.map((i) => i.title)).toEqual(["s1", "s2"]);
});

test("개별값(counts)이 있으면 그 분야만 개별 개수로 자른다", () => {
  const out = applySettings(makeDigest(), { globalCount: 2, counts: { 경제: 4 }, disabled: [] });
  const econ = out.categories.find((c) => c.name === "경제")!;
  const soc = out.categories.find((c) => c.name === "사회")!;
  expect(econ.items).toHaveLength(4); // 개별값 4
  expect(soc.items).toHaveLength(2); // globalCount 2
});

test("아이템이 개수보다 적으면 있는 만큼만", () => {
  const out = applySettings(makeDigest(), { globalCount: 10, counts: {}, disabled: [] });
  expect(out.categories.find((c) => c.name === "경제")!.items).toHaveLength(5);
  expect(out.categories.find((c) => c.name === "사회")!.items).toHaveLength(3);
});

test("disabled 분야는 제외한다", () => {
  const out = applySettings(makeDigest(), { globalCount: 10, counts: {}, disabled: ["사회"] });
  expect(out.categories.map((c) => c.name)).toEqual(["경제"]);
});

test("모든 분야가 disabled면 빈 목록이 된다(폴백 없음)", () => {
  const out = applySettings(makeDigest(), {
    globalCount: 10,
    counts: {},
    disabled: ["경제", "사회"],
  });
  expect(out.categories).toEqual([]);
});

test("입력 순서를 재정렬하지 않는다", () => {
  const out = applySettings(makeDigest(), { ...DEFAULT_SETTINGS, globalCount: 10 });
  const econ = out.categories.find((c) => c.name === "경제")!;
  expect(econ.items.map((i) => i.title)).toEqual(["e1", "e2", "e3", "e4", "e5"]);
});
