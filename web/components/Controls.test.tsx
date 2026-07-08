import { render, screen, fireEvent } from "@testing-library/react";
import Controls from "./Controls";
import { DEFAULT_SETTINGS } from "../lib/types";

test("4개 분야 체크박스와 경제 개수를 렌더한다", () => {
  render(
    <Controls settings={DEFAULT_SETTINGS} onToggleCategory={() => {}} onEconomyCount={() => {}} />
  );
  expect(screen.getByLabelText("경제")).toBeDefined();
  expect(screen.getByLabelText("IT/테크")).toBeDefined();
  expect(screen.getByText("10")).toBeDefined();
});

test("분야 체크박스 클릭 시 onToggleCategory 호출", () => {
  const spy = vi.fn();
  render(
    <Controls settings={DEFAULT_SETTINGS} onToggleCategory={spy} onEconomyCount={() => {}} />
  );
  fireEvent.click(screen.getByLabelText("사회"));
  expect(spy).toHaveBeenCalledWith("사회");
});

test("+/− 버튼이 현재값 기준으로 onEconomyCount 호출", () => {
  const spy = vi.fn();
  render(
    <Controls
      settings={{ ...DEFAULT_SETTINGS, economyCount: 5 }}
      onToggleCategory={() => {}}
      onEconomyCount={spy}
    />
  );
  fireEvent.click(screen.getByLabelText("늘리기"));
  expect(spy).toHaveBeenCalledWith(6);
  fireEvent.click(screen.getByLabelText("줄이기"));
  expect(spy).toHaveBeenCalledWith(4);
});
