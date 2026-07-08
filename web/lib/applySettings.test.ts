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
      { name: "사회", items: [item("s1"), item("s2")] },
    ],
  };
}

test("경제는 economyCount만큼 앞에서 자른다", () => {
  const out = applySettings(makeDigest(), { ...DEFAULT_SETTINGS, economyCount: 3 });
  const econ = out.categories.find((c) => c.name === "경제")!;
  expect(econ.items.map((i) => i.title)).toEqual(["e1", "e2", "e3"]);
});

test("경제 아이템이 개수보다 적으면 있는 만큼만", () => {
  const out = applySettings(makeDigest(), { ...DEFAULT_SETTINGS, economyCount: 10 });
  const econ = out.categories.find((c) => c.name === "경제")!;
  expect(econ.items).toHaveLength(5);
});

test("경제 외 분야는 자르지 않는다", () => {
  const out = applySettings(makeDigest(), { ...DEFAULT_SETTINGS, economyCount: 2 });
  const soc = out.categories.find((c) => c.name === "사회")!;
  expect(soc.items).toHaveLength(2);
});

test("enabledCategories에 없는 분야는 제외한다", () => {
  const out = applySettings(makeDigest(), { economyCount: 10, enabledCategories: ["경제"] });
  expect(out.categories.map((c) => c.name)).toEqual(["경제"]);
});

test("전부 꺼지면 전체를 표시한다(폴백)", () => {
  const out = applySettings(makeDigest(), { economyCount: 10, enabledCategories: [] });
  expect(out.categories.map((c) => c.name)).toEqual(["경제", "사회"]);
});

test("입력 순서를 재정렬하지 않는다", () => {
  const out = applySettings(makeDigest(), DEFAULT_SETTINGS);
  const econ = out.categories.find((c) => c.name === "경제")!;
  expect(econ.items.map((i) => i.title)).toEqual(["e1", "e2", "e3", "e4", "e5"]);
});
