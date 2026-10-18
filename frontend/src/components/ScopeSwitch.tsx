"use client";

import type { Scope } from "@/lib/useSiteScope";

/** "My sites" / "All sites" pill, same look as the model switch. */
export function ScopeSwitch({ value, onChange }: { value: Scope; onChange: (next: Scope) => void }) {
  return (
    <div role="group" aria-label="Which sites" className="flex rounded-full bg-raised p-0.5 text-[13px]">
      {(["mine", "all"] as const).map((s) => (
        <button
          key={s}
          type="button"
          aria-pressed={value === s}
          onClick={() => onChange(s)}
          className={`min-h-8 rounded-full px-3 transition-colors ${
            value === s ? "bg-accent-strong font-semibold text-on-accent" : "text-ink-2 hover:text-ink"
          }`}
        >
          {s === "mine" ? "My sites" : "All sites"}
        </button>
      ))}
    </div>
  );
}
