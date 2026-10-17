"use client";

import type { Scorer } from "@/lib/api";

export const MODEL_LABELS: Record<Scorer, string> = { ml: "Predictive (ML model)", rules: "Real-time (rules-v2)" };

const OPTIONS: { value: Scorer; label: string; title: string }[] = [
  { value: "rules", label: "Real-time", title: "Rules-v2: OSHA/NWS work-rule thresholds on current heat, storms, wind, rain and alerts" },
  { value: "ml", label: "Predictive", title: "ML model: XGBoost trained on 2023-2025 weather and NOAA storm records" },
];

/** Pill that switches the map and ranked list between scorers. Sits over the map's top-right corner. */
export function ModelSwitch({ value, onChange }: { value: Scorer; onChange: (next: Scorer) => void }) {
  return (
    <div
      role="group"
      aria-label="Risk model"
      className="flex rounded-full border border-line bg-card/90 p-0.5 text-xs font-medium shadow-lg backdrop-blur"
    >
      {OPTIONS.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            title={o.title}
            onClick={() => onChange(o.value)}
            className={`rounded-full px-3 py-1.5 transition-colors ${
              active ? "bg-accent-strong text-white" : "text-ink-2 hover:text-ink"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
