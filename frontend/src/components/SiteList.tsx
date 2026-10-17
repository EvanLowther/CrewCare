"use client";

import type { SiteSummary } from "@/lib/api";
import { ALERT_ICONS, ALERT_LABELS } from "@/lib/alerts";
import { REVEAL_SPREAD_MS } from "@/lib/useModelSwitch";
import { ScoreChip } from "./ui";

/**
 * Sites ranked by risk (the API already sorts them, highest first). `hidden` fades the list out while the model
 * switches; a `revealKey` replays the rows in from top to bottom.
 */
export function SiteList({
  sites,
  selectedId,
  onSelect,
  hidden = false,
  revealKey = null,
}: {
  sites: SiteSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  hidden?: boolean;
  revealKey?: number | null;
}) {
  const step = sites.length > 1 ? REVEAL_SPREAD_MS / (sites.length - 1) : 0;
  return (
    // A new key per reveal remounts the rows so their animation plays again.
    <ol
      key={revealKey ?? "steady"}
      className={`divide-y divide-line transition-opacity duration-300 ${hidden ? "opacity-0" : ""}`}
    >
      {sites.map((site, i) => {
        const selected = site.id === selectedId;
        const AlertIcon = site.top_alert ? ALERT_ICONS[site.top_alert] : null;
        return (
          <li
            key={site.id}
            className={revealKey !== null ? "reveal-row" : undefined}
            style={revealKey !== null ? { animationDelay: `${Math.round(i * step)}ms` } : undefined}
          >
            <button
              type="button"
              onClick={() => onSelect(site.id)}
              aria-current={selected ? "true" : undefined}
              className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-raised ${
                selected ? "bg-accent-soft" : ""
              }`}
            >
              <span className="tabular w-5 shrink-0 text-right text-xs text-muted">{i + 1}</span>
              <ScoreChip score={site.risk?.score ?? null} level={site.risk?.level ?? null} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-ink">{site.name}</span>
                <span className="flex items-center gap-1 truncate text-xs text-muted">
                  {site.top_alert && AlertIcon ? (
                    <>
                      <AlertIcon className="h-3 w-3 shrink-0 text-[#ff9b9b]" aria-hidden />
                      <span className="text-[#ff9b9b]">{ALERT_LABELS[site.top_alert]}</span>
                    </>
                  ) : (
                    (site.risk?.factors[0]?.label ?? `${site.county} County`)
                  )}
                </span>
              </span>
              {site.heat_index_f !== null && (
                <span className="tabular shrink-0 text-xs text-ink-2">{Math.round(site.heat_index_f)}°F</span>
              )}
            </button>
          </li>
        );
      })}
    </ol>
  );
}
