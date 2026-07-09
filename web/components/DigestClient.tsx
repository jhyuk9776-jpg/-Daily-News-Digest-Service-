"use client";
import { useDigestSettings } from "../lib/useDigestSettings";
import { applySettings, totalShown } from "../lib/applySettings";
import Controls from "./Controls";
import CopyKakaoButton from "./CopyKakaoButton";
import DigestView from "./Digest";
import type { Digest } from "../lib/types";

export default function DigestClient({ digest }: { digest: Digest }) {
  const names = digest.categories.map((c) => c.name);
  const { settings, countOf, setCount, setGlobalCount, reset } = useDigestSettings(names);
  const view = applySettings(digest, settings);
  return (
    <main>
      {/* UX 순서: ① 제목(서비스 파악) → ② 메뉴(기능 짐작) → ③ 본문 */}
      <h1>오늘의 뉴스 요약 — {digest.date}</h1>
      <Controls
        categories={names}
        globalCount={settings.globalCount}
        countOf={countOf}
        totalShown={totalShown(digest, settings)}
        onSetCount={setCount}
        onSetGlobalCount={setGlobalCount}
        onReset={reset}
        actions={<CopyKakaoButton digest={view} />}
      />
      <DigestView digest={view} />
    </main>
  );
}
