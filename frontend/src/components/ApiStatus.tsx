"use client";

import { useEffect, useState } from "react";
import { api, type Health } from "@/lib/api";

/** Shows whether the frontend can reach the API, and whether it's serving mock data. */
export function ApiStatus() {
  const [health, setHealth] = useState<Health | null>(null);
  const [siteCount, setSiteCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch((e: Error) => setError(e.message));
    api.sites().then((r) => setSiteCount(r.sites.length)).catch(() => setSiteCount(null));
  }, []);

  if (error) return <p className="text-sm text-red-600">API unreachable: {error}. Is `python dev.py api` running?</p>;
  if (!health) return <p className="text-sm text-neutral-500">Checking API…</p>;
  return (
    <p className="text-sm text-neutral-600">
      API ok · {health.mock ? "mock data" : "live data"} · database {health.database}
      {siteCount !== null && ` · ${siteCount} sites`}
    </p>
  );
}
