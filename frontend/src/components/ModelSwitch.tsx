"use client";

import type { Scorer } from "@/lib/api";

const OPTIONS: { value: Scorer; label: string; title: string }[] = [
  { value: "rules", label: "Real-time", title: "Rules-v1: hand-set thresholds on current heat, rain, wind and alerts" },
  { value: "ml", label: "Predictive", title: "ML model: XGBoost trained on 2023-2025 weather and NOAA storm records" },
];

/** Pill that switches the map and ranked list between scorers. Sits over the map's top-right corner. */
export function ModelSwitch({
  value,
  onChange,
  busy,
}: {
  value: Scorer;
  onChange: (next: Scorer) => void;
  busy: boolean;
}) {
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
            disabled={busy && !active}
            onClick={() => onChange(o.value)}
            className={`rounded-full px-3 py-1.5 transition-colors disabled:cursor-wait ${
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
