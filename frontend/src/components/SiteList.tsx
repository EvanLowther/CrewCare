"use client";

import type { SiteSummary } from "@/lib/api";
import { ALERT_ICONS, ALERT_LABELS } from "@/lib/alerts";
import { RISK_COLORS } from "@/lib/risk";

/** Sites ranked by risk (the API already sorts them, highest first). */
export function SiteList({
  sites,
  selectedId,
  onSelect,
}: {
  sites: SiteSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <ol className="divide-y divide-neutral-200">
      {sites.map((site, i) => {
        const selected = site.id === selectedId;
        return (
          <li key={site.id}>
            <button
              type="button"
              onClick={() => onSelect(site.id)}
              aria-current={selected ? "true" : undefined}
              className={`flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-neutral-100 ${
                selected ? "bg-blue-50" : ""
              }`}
            >
              <span className="w-5 shrink-0 text-right text-xs text-neutral-400">{i + 1}</span>
              <span
                className="flex h-9 w-11 shrink-0 items-center justify-center rounded-md text-sm font-bold text-white"
                style={{ background: site.risk ? RISK_COLORS[site.risk.level] : "#6b7280" }}
              >
                {site.risk ? site.risk.score.toFixed(1) : "–"}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{site.name}</span>
                <span className="block truncate text-xs text-neutral-500">
                  {site.top_alert
                    ? `${ALERT_ICONS[site.top_alert]} ${ALERT_LABELS[site.top_alert]}`
                    : (site.risk?.factors[0]?.label ?? site.county)}
                </span>
              </span>
              {site.heat_index_f !== null && (
                <span className="shrink-0 text-xs text-neutral-500">{Math.round(site.heat_index_f)}°F</span>
              )}
            </button>
          </li>
        );
      })}
    </ol>
  );
}
