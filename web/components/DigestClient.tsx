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
    <>
      <Controls
        categories={names}
        globalCount={settings.globalCount}
        countOf={countOf}
        totalShown={totalShown(digest, settings)}
        onSetCount={setCount}
        onSetGlobalCount={setGlobalCount}
        onReset={reset}
      />
      <div className="copy-bar">
        <CopyKakaoButton digest={view} />
      </div>
      <DigestView digest={view} />
    </>
  );
}
