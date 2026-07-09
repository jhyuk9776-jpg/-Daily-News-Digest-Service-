"use client";
import { useState } from "react";
import type { Digest } from "../lib/types";
import { buildKakaoText } from "../lib/kakaoText";

// 현재 화면 기준 카톡용 plain 텍스트를 클립보드로 원클릭 복사.
// (이메일은 JS가 막혀 이 버튼을 넣을 수 없어 웹 전용.)
export default function CopyKakaoButton({ digest }: { digest: Digest }) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(buildKakaoText(digest));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button className="copy-kakao" onClick={onCopy}>
      {copied ? "복사됨 ✓" : "카톡용 복사"}
    </button>
  );
}
