import React from "react";

// Liquid Glass 버튼 — Tailwind/shadcn 없이 순수 CSS로 구현한 동일 API.
// 프로스트 유리 레이어(backdrop-filter) + 상단 하이라이트 + (Chromium) 굴절 왜곡.
// 스타일은 globals.css의 .liquid-button 계열, 굴절 필터는 layout의 전역 SVG(#liquid-glass).
export interface LiquidButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  className?: string;
}

export function LiquidButton({ className = "", children, ...props }: LiquidButtonProps) {
  return (
    <button className={`liquid-button ${className}`.trim()} {...props}>
      <span className="liquid-button__glass" aria-hidden="true" />
      <span className="liquid-button__shine" aria-hidden="true" />
      <span className="liquid-button__label">{children}</span>
    </button>
  );
}

export default LiquidButton;
