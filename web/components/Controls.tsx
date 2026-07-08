"use client";
import type { DigestSettings } from "../lib/types";
import { ALL_CATEGORIES } from "../lib/types";

export default function Controls({
  settings,
  onToggleCategory,
  onEconomyCount,
}: {
  settings: DigestSettings;
  onToggleCategory: (name: string) => void;
  onEconomyCount: (n: number) => void;
}) {
  return (
    <div className="controls">
      <div className="controls-filters">
        {ALL_CATEGORIES.map((name) => (
          <label key={name} className="filter-chip">
            <input
              type="checkbox"
              checked={settings.enabledCategories.includes(name)}
              onChange={() => onToggleCategory(name)}
            />
            {name}
          </label>
        ))}
      </div>
      <div className="controls-count">
        <span>경제 표시</span>
        <button aria-label="줄이기" onClick={() => onEconomyCount(settings.economyCount - 1)}>
          −
        </button>
        <span className="count-value">{settings.economyCount}</span>
        <button aria-label="늘리기" onClick={() => onEconomyCount(settings.economyCount + 1)}>
          +
        </button>
      </div>
    </div>
  );
}
