"use client";

export default function Controls({
  categories,
  globalCount,
  countOf,
  isEnabled,
  onToggleCategory,
  onSetCount,
  onSetGlobalCount,
  onReset,
}: {
  categories: string[];
  globalCount: number;
  countOf: (name: string) => number;
  isEnabled: (name: string) => boolean;
  onToggleCategory: (name: string) => void;
  onSetCount: (name: string, n: number) => void;
  onSetGlobalCount: (n: number) => void;
  onReset: () => void;
}) {
  return (
    <div className="controls">
      <div className="controls-categories">
        {categories.map((name) => (
          <div key={name} className="category-row">
            <label className="filter-chip">
              <input
                type="checkbox"
                checked={isEnabled(name)}
                onChange={() => onToggleCategory(name)}
              />
              {name}
            </label>
            <div className="count-stepper">
              <button
                aria-label={`${name} 줄이기`}
                onClick={() => onSetCount(name, countOf(name) - 1)}
              >
                −
              </button>
              <span className="count-value">{countOf(name)}</span>
              <button
                aria-label={`${name} 늘리기`}
                onClick={() => onSetCount(name, countOf(name) + 1)}
              >
                +
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="controls-global">
        <span className="global-label">전체</span>
        <div className="count-stepper">
          <button aria-label="전체 줄이기" onClick={() => onSetGlobalCount(globalCount - 1)}>
            −
          </button>
          <span className="count-value">{globalCount}</span>
          <button aria-label="전체 늘리기" onClick={() => onSetGlobalCount(globalCount + 1)}>
            +
          </button>
        </div>
        <button className="reset-btn" onClick={onReset}>
          기본값으로 되돌리기
        </button>
      </div>
    </div>
  );
}
