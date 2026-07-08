"use client";
import { useDigestSettings } from "../lib/useDigestSettings";
import { applySettings } from "../lib/applySettings";
import Controls from "./Controls";
import DigestView from "./Digest";
import type { Digest } from "../lib/types";

export default function DigestClient({ digest }: { digest: Digest }) {
  const names = digest.categories.map((c) => c.name);
  const {
    settings,
    countOf,
    isEnabled,
    setCount,
    setGlobalCount,
    toggleCategory,
    reset,
  } = useDigestSettings(names);
  const view = applySettings(digest, settings);
  return (
    <>
      <Controls
        categories={names}
        globalCount={settings.globalCount}
        countOf={countOf}
        isEnabled={isEnabled}
        onToggleCategory={toggleCategory}
        onSetCount={setCount}
        onSetGlobalCount={setGlobalCount}
        onReset={reset}
      />
      <DigestView digest={view} />
    </>
  );
}
