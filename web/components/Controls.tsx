"use client";
import { COUNT_OPTIONS } from "../lib/types";

export default function Controls({
  categories,
  globalCount,
  countOf,
  totalShown,
  onSetCount,
  onSetGlobalCount,
  onReset,
}: {
  categories: string[];
  globalCount: number;
  countOf: (name: string) => number;
  totalShown: number;
  onSetCount: (name: string, n: number) => void;
  onSetGlobalCount: (n: number) => void;
  onReset: () => void;
}) {
  return (
    <div className="controls">
      <div className="controls-categories">
        {categories.map((name) => (
          <div key={name} className="category-row">
            <span className="category-name">{name}</span>
            <select
              className="count-select"
              aria-label={`${name} 표시 개수`}
              value={countOf(name)}
              onChange={(e) => onSetCount(name, Number(e.target.value))}
            >
              {COUNT_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n === 0 ? "숨김" : `${n}건`}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>

      <div className="controls-global">
        <span className="global-label">전체</span>
        <select
          className="count-select"
          aria-label="전체 표시 개수"
          value={globalCount}
          onChange={(e) => onSetGlobalCount(Number(e.target.value))}
        >
          {COUNT_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n === 0 ? "숨김" : `${n}건`}
            </option>
          ))}
        </select>
        <span className="total-shown">총 {totalShown}건 표시 중</span>
        <button className="reset-btn" onClick={onReset}>
          기본값으로 되돌리기
        </button>
      </div>
    </div>
  );
}
