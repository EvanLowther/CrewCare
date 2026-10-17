"use client";

import { useEffect, useState } from "react";

/**
 * Calls `fetcher` now and every `intervalMs`, pausing while the tab is hidden.
 * `fetcher` must be stable (e.g. `api.sites`, or wrapped in useCallback) or polling restarts every render.
 */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs = 10_000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      if (document.hidden) return;
      fetcher()
        .then((d) => {
          if (cancelled) return;
          setData(d);
          setError(null);
        })
        .catch((e: Error) => !cancelled && setError(e.message));
    };
    load();
    const timer = setInterval(load, intervalMs);
    document.addEventListener("visibilitychange", load);
    return () => {
      cancelled = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", load);
    };
  }, [fetcher, intervalMs]);

  return { data, error };
}
