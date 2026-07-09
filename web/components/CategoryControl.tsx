"use client";
import { COUNT_OPTIONS } from "../lib/types";

// 분야명 + 개수 드롭다운을 하나의 유리 pill로 묶은 컨트롤(카톡 복사·되돌리기 버튼과 같은 모양).
export default function CategoryControl({
  name,
  count,
  onChange,
}: {
  name: string;
  count: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="category-chip">
      <span className="category-chip__name">{name}</span>
      <select
        className="category-chip__select"
        aria-label={`${name} 표시 개수`}
        value={count}
        onChange={(e) => onChange(Number(e.target.value))}
      >
        {COUNT_OPTIONS.map((n) => (
          <option key={n} value={n}>
            {n === 0 ? "숨김" : `${n}건`}
          </option>
        ))}
      </select>
    </div>
  );
}
