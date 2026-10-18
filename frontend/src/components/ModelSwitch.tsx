"use client";

import type { Scorer } from "@/lib/api";

export const MODEL_LABELS: Record<Scorer, string> = { ml: "Predictive (ML model)", rules: "Real-time data" };

const OPTIONS: { value: Scorer; label: string; short: string; title: string }[] = [
  { value: "rules", label: "Real-time data", short: "Real-time", title: "Rules-v2: OSHA/NWS work-rule thresholds on current heat, storms, wind, rain and alerts" },
  { value: "ml", label: "Predictive model", short: "Predictive", title: "ML model: XGBoost trained on 2023-2025 weather and NOAA storm records" },
];

/** Segmented switch between scorers: the map, ranked list and site page all follow it. */
export function ModelSwitch({
  value,
  onChange,
  full = false,
}: {
  value: Scorer;
  onChange: (next: Scorer) => void;
  /** Stretch to the container and use the long labels (the dashboard panel). */
  full?: boolean;
}) {
  return (
    <div role="group" aria-label="Risk model" className={`flex rounded-[10px] border border-line bg-[#0c1018] p-1 ${full ? "w-full" : ""}`}>
      {OPTIONS.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            title={o.title}
            onClick={() => onChange(o.value)}
            className={`min-h-9 rounded-[7px] px-3.5 text-[13px] transition-colors ${full ? "flex-1" : ""} ${
              active ? "bg-accent-strong font-semibold text-on-accent" : "text-ink-2 hover:text-ink"
            }`}
          >
            {full ? o.label : o.short}
          </button>
        );
      })}
    </div>
  );
}
