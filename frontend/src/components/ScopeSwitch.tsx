"use client";

import type { Scope } from "@/lib/useSiteScope";

/** "My sites" / "All sites" pill, same look as the model switch. */
export function ScopeSwitch({ value, onChange }: { value: Scope; onChange: (next: Scope) => void }) {
  return (
    <div role="group" aria-label="Which sites" className="flex rounded-full border border-line bg-card p-0.5 text-xs font-medium">
      {(["mine", "all"] as const).map((s) => (
        <button
          key={s}
          type="button"
          aria-pressed={value === s}
          onClick={() => onChange(s)}
          className={`rounded-full px-3 py-1.5 transition-colors ${
            value === s ? "bg-accent-strong text-white" : "text-ink-2 hover:text-ink"
          }`}
        >
          {s === "mine" ? "My sites" : "All sites"}
        </button>
      ))}
    </div>
  );
}
