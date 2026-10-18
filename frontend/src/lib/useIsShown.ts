"use client";

import { useLayoutEffect, useState } from "react";

/**
 * True while this component's page is on screen.
 *
 * With Cache Components, Next 16 keeps pages you navigate away from alive but hidden (React <Activity>) and
 * re-runs their effects when you come back. Leaflet maps can't survive that: react-leaflet removes the map when
 * the page hides, then its markers and tiles try to re-attach to the removed map when it shows again, and the page
 * crashes ("This page couldn't load"). Render a map only when this is true, so it's unmounted while hidden and
 * built fresh on return. A layout effect, so it runs before the page is hidden or shown (docs: Preserving UI state).
 */
export function useIsShown(): boolean {
  const [shown, setShown] = useState(false);
  useLayoutEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setShown(true);
    return () => setShown(false);
  }, []);
  return shown;
}
