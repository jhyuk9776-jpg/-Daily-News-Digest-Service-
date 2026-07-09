import { render, screen, fireEvent } from "@testing-library/react";
import Controls from "./Controls";

const CATS = ["경제", "사회", "세계", "IT/테크"];

function renderControls(overrides = {}) {
  const props = {
    categories: CATS,
    globalCount: 2,
    countOf: (name: string) => (name === "경제" ? 5 : 2),
    totalShown: 11,
    onSetCount: vi.fn(),
    onSetGlobalCount: vi.fn(),
    onReset: vi.fn(),
    ...overrides,
  };
  render(<Controls {...props} />);
  return props;
}

test("분야별 드롭다운·전체 드롭다운·총계·되돌리기를 렌더한다", () => {
  renderControls();
  expect(screen.getByLabelText("경제 표시 개수")).toBeDefined();
  expect(screen.getByLabelText("IT/테크 표시 개수")).toBeDefined();
  expect(screen.getByLabelText("전체 표시 개수")).toBeDefined();
  expect(screen.getByText("총 11건 표시 중")).toBeDefined();
  expect(screen.getByText("기본값으로 되돌리기")).toBeDefined();
});

test("분야 드롭다운은 현재값을 반영하고 변경 시 onSetCount 호출", () => {
  const props = renderControls();
  const sel = screen.getByLabelText("경제 표시 개수") as HTMLSelectElement;
  expect(sel.value).toBe("5");
  fireEvent.change(sel, { target: { value: "0" } });
  expect(props.onSetCount).toHaveBeenCalledWith("경제", 0);
});

test("전체 드롭다운은 현재값을 반영하고 변경 시 onSetGlobalCount 호출", () => {
  const props = renderControls({ globalCount: 3 });
  const sel = screen.getByLabelText("전체 표시 개수") as HTMLSelectElement;
  expect(sel.value).toBe("3");
  fireEvent.change(sel, { target: { value: "7" } });
  expect(props.onSetGlobalCount).toHaveBeenCalledWith(7);
});

test("0=숨김 옵션이 드롭다운에 존재한다", () => {
  renderControls();
  expect(screen.getAllByText("숨김").length).toBeGreaterThan(0);
});

test("되돌리기 버튼 클릭 시 onReset 호출", () => {
  const props = renderControls();
  fireEvent.click(screen.getByText("기본값으로 되돌리기"));
  expect(props.onReset).toHaveBeenCalled();
});
