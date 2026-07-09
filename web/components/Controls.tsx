"use client";
import type { ReactNode } from "react";
import CategoryControl from "./CategoryControl";
import { LiquidButton } from "@/components/ui/liquid-glass-button";

export default function Controls({
  categories,
  globalCount,
  countOf,
  totalShown,
  onSetCount,
  onSetGlobalCount,
  onReset,
  actions,
}: {
  categories: string[];
  globalCount: number;
  countOf: (name: string) => number;
  totalShown: number;
  onSetCount: (name: string, n: number) => void;
  onSetGlobalCount: (n: number) => void;
  onReset: () => void;
  actions?: ReactNode;
}) {
  return (
    <div className="controls">
      <div className="controls-categories">
        {categories.map((name) => (
          <CategoryControl
            key={name}
            name={name}
            count={countOf(name)}
            onChange={(n) => onSetCount(name, n)}
          />
        ))}
      </div>

      <div className="controls-global">
        <CategoryControl name="전체" count={globalCount} onChange={onSetGlobalCount} />
        <span className="total-shown">총 {totalShown}건 표시 중</span>
        {actions}
        <LiquidButton className="liquid-button--ghost" onClick={onReset}>
          기본값으로 되돌리기
        </LiquidButton>
      </div>
    </div>
  );
}
