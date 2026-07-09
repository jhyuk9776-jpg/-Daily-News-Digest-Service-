import { render, screen, fireEvent } from "@testing-library/react";
import Controls from "./Controls";

const CATS = ["경제", "사회", "세계", "IT/테크"];

function renderControls(overrides = {}) {
  const props = {
    categories: CATS,
    globalCount: 2,
    countOf: (name: string) => (name === "경제" ? 5 : 2),
    isEnabled: () => true,
    onToggleCategory: vi.fn(),
    onSetCount: vi.fn(),
    onSetGlobalCount: vi.fn(),
    onReset: vi.fn(),
    ...overrides,
  };
  render(<Controls {...props} />);
  return props;
}

test("분야별 체크박스·개수·전체·되돌리기를 렌더한다", () => {
  renderControls();
  expect(screen.getByLabelText("경제")).toBeDefined();
  expect(screen.getByLabelText("IT/테크")).toBeDefined();
  expect(screen.getByText("기본값으로 되돌리기")).toBeDefined();
  // 경제 개별 개수 5, 전체 2가 각각 보인다
  expect(screen.getByLabelText("경제 늘리기")).toBeDefined();
  expect(screen.getByLabelText("전체 늘리기")).toBeDefined();
});

test("분야 체크박스 클릭 시 onToggleCategory 호출", () => {
  const props = renderControls();
  fireEvent.click(screen.getByLabelText("사회"));
  expect(props.onToggleCategory).toHaveBeenCalledWith("사회");
});

test("분야별 +/− 는 그 분야의 현재값 기준으로 onSetCount 호출", () => {
  const props = renderControls();
  fireEvent.click(screen.getByLabelText("경제 늘리기"));
  expect(props.onSetCount).toHaveBeenCalledWith("경제", 6); // 5 → 6
  fireEvent.click(screen.getByLabelText("경제 줄이기"));
  expect(props.onSetCount).toHaveBeenCalledWith("경제", 4); // 5 → 4
});

test("전체 +/− 는 globalCount 기준으로 onSetGlobalCount 호출", () => {
  const props = renderControls({ globalCount: 3 });
  fireEvent.click(screen.getByLabelText("전체 늘리기"));
  expect(props.onSetGlobalCount).toHaveBeenCalledWith(4);
  fireEvent.click(screen.getByLabelText("전체 줄이기"));
  expect(props.onSetGlobalCount).toHaveBeenCalledWith(2);
});

test("되돌리기 버튼 클릭 시 onReset 호출", () => {
  const props = renderControls();
  fireEvent.click(screen.getByText("기본값으로 되돌리기"));
  expect(props.onReset).toHaveBeenCalled();
});
