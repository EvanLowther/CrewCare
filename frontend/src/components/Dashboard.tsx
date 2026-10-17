"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { api } from "@/lib/api";
import { RISK_COLORS, RISK_LABELS } from "@/lib/risk";
import { usePolling } from "@/lib/usePolling";
import { SiteList } from "./SiteList";

// Leaflet needs `window`, so the map only renders in the browser.
const SiteMap = dynamic(() => import("./SiteMap"), {
  ssr: false,
  loading: () => <div className="flex h-full items-center justify-center text-neutral-400">Loading map…</div>,
});

const POLL_MS = 10_000;

export function Dashboard() {
  const { data, error } = usePolling(api.sites, POLL_MS);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const sites = data?.sites ?? [];
  const alerting = sites.filter((s) => s.active_alert_count > 0).length;
  const anyScored = sites.some((s) => s.risk !== null);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Site risk dashboard</h1>
          <p className="text-sm text-neutral-500">
            {data
              ? `${sites.length} sites · ${alerting} with active alerts · updated ${new Date(data.updated_at).toLocaleTimeString()}`
              : "Loading sites…"}
          </p>
        </div>
        <Legend />
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          Can&apos;t reach the API ({error}). Is <code>python dev.py api</code> running? Retrying every 10 s.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <div className="h-[55vh] overflow-hidden rounded-lg border border-neutral-200 bg-white lg:h-[calc(100vh-11rem)]">
          <SiteMap sites={sites} selectedId={selectedId} onSelect={setSelectedId} />
        </div>
        <aside className="overflow-hidden rounded-lg border border-neutral-200 bg-white lg:h-[calc(100vh-11rem)]">
          <h2 className="border-b border-neutral-200 px-3 py-2 text-sm font-semibold">
            {anyScored || !data ? "Highest risk first" : "Largest plants first · no risk scores yet"}
          </h2>
          <div className="lg:h-[calc(100%-2.3rem)] lg:overflow-y-auto">
            <SiteList sites={sites} selectedId={selectedId} onSelect={setSelectedId} />
          </div>
        </aside>
      </div>
    </div>
  );
}

function Legend() {
  return (
    <ul className="flex flex-wrap gap-3 text-xs text-neutral-600">
      {(Object.keys(RISK_COLORS) as (keyof typeof RISK_COLORS)[]).map((level) => (
        <li key={level} className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full" style={{ background: RISK_COLORS[level] }} />
          {RISK_LABELS[level]}
        </li>
      ))}
    </ul>
  );
}
