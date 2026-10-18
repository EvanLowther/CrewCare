"use client";

import { useEffect, useState } from "react";

/**
 * Calls `fetcher` now and every `intervalMs`, pausing while the tab is hidden.
 * `fetcher` must be stable (e.g. `api.sites`, or wrapped in useCallback) or polling restarts every render.
 *
 * Once there is data, one failed poll is ignored (the last data stays up); `error` is set after two in a row, so a
 * blip like a server restart doesn't flash an error. Before the first data, any failure shows at once.
 */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs = 10_000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    let hasData = false;
    let failures = 0;
    const load = () => {
      if (document.hidden) return;
      fetcher()
        .then((d) => {
          if (cancelled) return;
          hasData = true;
          failures = 0;
          setData(d);
          setError(null);
        })
        .catch((e: Error) => {
          if (cancelled) return;
          failures += 1;
          if (!hasData || failures >= 2) setError(e.message);
        });
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
