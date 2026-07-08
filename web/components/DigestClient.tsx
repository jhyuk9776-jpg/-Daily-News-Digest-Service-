"use client";
import { useDigestSettings } from "../lib/useDigestSettings";
import { applySettings } from "../lib/applySettings";
import Controls from "./Controls";
import DigestView from "./Digest";
import type { Digest } from "../lib/types";

export default function DigestClient({ digest }: { digest: Digest }) {
  const { settings, setEconomyCount, toggleCategory } = useDigestSettings();
  const view = applySettings(digest, settings);
  return (
    <>
      <Controls
        settings={settings}
        onToggleCategory={toggleCategory}
        onEconomyCount={setEconomyCount}
      />
      <DigestView digest={view} />
    </>
  );
}
