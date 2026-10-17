"use client";

import { useEffect, useRef, useState } from "react";
import type { Scorer, SiteList } from "./api";

export const MODEL_LABELS: Record<Scorer, string> = { ml: "ML model (XGBoost)", rules: "Rules-v1" };

/** Fade-out before the switch, and the window the reveal is spread over (plus one item's animation ≈ 3 s). */
export const HIDE_MS = 300;
export const REVEAL_SPREAD_MS = 2600;
export const REVEAL_ITEM_MS = 450;
const GIVE_UP_MS = 8000; // if the new scores never arrive, reveal whatever we have

type Phase = "idle" | "hiding" | "revealing";

/** Which scorer produced a site list ('ml' for xgb-* versions), or null when no site has a score. */
export function scorerOf(list: SiteList): Scorer | null {
  const version = list.sites.find((s) => s.risk)?.risk?.model_version;
  return version ? (version.startsWith("xgb") ? "ml" : "rules") : null;
}

/**
 * Switching the dashboard between scorers: fade the pins and list out, wait for the other scorer's sites, then
 * reveal them over ~3 s. While animating, the sites shown are a frozen snapshot so a poll can't restart it.
 * `data` is the polled site list for `model`; the caller refetches when `model` changes.
 */
export function useModelSwitch(model: Scorer, setModel: (m: Scorer) => void, data: SiteList | null) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [frozen, setFrozen] = useState<SiteList | null>(null);
  const [revealKey, setRevealKey] = useState(0);
  const hiddenAt = useRef(0);

  const reveal = (list: SiteList | null) => {
    setFrozen(list);
    setRevealKey((k) => k + 1);
    setPhase("revealing");
  };

  // hiding -> revealing once the new scorer's sites are here and the fade-out has finished.
  useEffect(() => {
    if (phase !== "hiding") return;
    const giveUp = setTimeout(() => reveal(data), GIVE_UP_MS - (Date.now() - hiddenAt.current));
    if (!data || (scorerOf(data) !== null && scorerOf(data) !== model)) return () => clearTimeout(giveUp);
    const ready = setTimeout(() => reveal(data), Math.max(0, HIDE_MS - (Date.now() - hiddenAt.current)));
    return () => {
      clearTimeout(giveUp);
      clearTimeout(ready);
    };
  }, [phase, data, model]);

  // revealing -> idle after the last item has animated in; live polls show again.
  useEffect(() => {
    if (phase !== "revealing") return;
    const done = setTimeout(() => {
      setPhase("idle");
      setFrozen(null);
    }, REVEAL_SPREAD_MS + REVEAL_ITEM_MS);
    return () => clearTimeout(done);
  }, [phase, revealKey]);

  const switchTo = (next: Scorer) => {
    if (phase !== "idle" || next === model) return;
    setModel(next);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return; // just swap when data arrives
    hiddenAt.current = Date.now();
    setFrozen(data);
    setPhase("hiding");
  };

  const shown = phase === "idle" ? data : frozen;
  return {
    sites: shown?.sites ?? [],
    updatedAt: shown?.updated_at ?? null,
    loaded: shown !== null,
    hidden: phase === "hiding",
    /** Changes for each reveal; null when not revealing. Components key their animation on it. */
    revealKey: phase === "revealing" ? revealKey : null,
    busy: phase !== "idle",
    switchTo,
  };
}
