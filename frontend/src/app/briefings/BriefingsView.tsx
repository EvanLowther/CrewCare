"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { CloudLightning, FileText, Haze, RefreshCw, Snowflake, ThermometerSun, Wind } from "lucide-react";
import { useMe } from "@/components/MeProvider";
import { ScopeSwitch } from "@/components/ScopeSwitch";
import { Card, CardHeader, EmptyState, ErrorBanner, PageHeader, ScoreChip } from "@/components/ui";
import { api, type Briefing } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { levelFor } from "@/lib/risk";
import { usePolling } from "@/lib/usePolling";
import { useSiteScope } from "@/lib/useSiteScope";

type Day = "tomorrow" | "today";

/** The facts the worker stores with each briefing (backend/planit/worker/briefing/generate.py build_facts). */
type Facts = {
  risk_score?: number | null;
  peak_heat_index_f?: number | null;
  peak_heat_time?: string | null;
  storm_window?: string | null;
  max_gust_mph?: number | null;
  snowfall_in?: number | null;
  min_wind_chill_f?: number | null;
  peak_smoke_aqi?: number | null;
  nws_alerts?: string[];
  recommendations?: string[];
};

/** YYYY-MM-DD in the viewer's own timezone, `days` from today. */
function localDate(days: number): string {
  const d = new Date(Date.now() + days * 86_400_000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Tomorrow's (or today's) safety briefing for every site the viewer may see, riskiest first. */
export function BriefingsView() {
  const { role } = useMe();
  const scope = useSiteScope();
  const [day, setDay] = useState<Day>("tomorrow");
  // The date is read when fetching, not during render (the page is prerendered).
  const fetchBriefings = useCallback(() => api.briefings(localDate(day === "tomorrow" ? 1 : 0)), [day]);
  const { data, error } = usePolling(fetchBriefings, 30_000);
  const briefings = (data?.briefings ?? []).filter((b) => scope.includes(b.site_id));

  const [ack, setAck] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const generate = async () => {
    setBusy(true);
    try {
      setAck((await api.generateBriefings()).message);
    } catch (e) {
      setAck(`Couldn't start: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Briefings"
        subtitle="Next-day safety briefing for every site, written at 6 PM in each site's local time."
        actions={
          <div className="flex flex-wrap items-center gap-3">
            {scope.available && <ScopeSwitch value={scope.scope} onChange={scope.setScope} />}
            <div role="group" aria-label="Day" className="flex rounded-[10px] border border-line bg-[#0c1018] p-1">
              {(["tomorrow", "today"] as Day[]).map((d) => (
                <button
                  key={d}
                  type="button"
                  aria-pressed={day === d}
                  onClick={() => setDay(d)}
                  className={`min-h-9 rounded-[7px] px-3.5 text-[13px] capitalize transition-colors ${
                    day === d ? "bg-accent-strong font-semibold text-on-accent" : "text-ink-2 hover:text-ink"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
            {role === "admin" && (
              <button
                type="button"
                onClick={generate}
                disabled={busy}
                className="inline-flex min-h-9 items-center gap-2 rounded-lg bg-accent-strong px-4 text-sm font-medium text-on-accent hover:bg-accent disabled:opacity-40"
              >
                <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} aria-hidden />
                Generate now
              </button>
            )}
          </div>
        }
      />
      {error && <ErrorBanner message={error} retrying />}
      {ack && <p className="rounded-lg border border-line bg-card px-4 py-2 text-sm text-ink-2">{ack}</p>}

      <Card className="overflow-hidden">
        <CardHeader
          title={day === "tomorrow" ? "Tomorrow's briefings" : "Today's briefings"}
          icon={FileText}
          subtitle={data ? `${briefings.length} ${briefings.length === 1 ? "site" : "sites"} · riskiest first` : "Loading…"}
        />
        {data && briefings.length === 0 ? (
          <EmptyState
            icon={FileText}
            title={`No briefings for ${day} yet`}
            detail="Each site's briefing is written at 6 PM in its local time. Admins can generate them now."
          />
        ) : (
          <ul className="divide-y divide-line border-t border-line">
            {briefings.map((b) => (
              <BriefingRow key={b.id} briefing={b} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function BriefingRow({ briefing: b }: { briefing: Briefing }) {
  const f = b.details as Facts;
  const score = f.risk_score ?? null;
  const chips = [
    f.peak_heat_index_f != null && f.peak_heat_index_f >= 90
      ? { icon: ThermometerSun, text: `Heat ${f.peak_heat_index_f}°F${f.peak_heat_time ? ` · ${f.peak_heat_time}` : ""}` }
      : null,
    f.storm_window ? { icon: CloudLightning, text: `Storms ${f.storm_window}` } : null,
    f.max_gust_mph != null && f.max_gust_mph >= 20 ? { icon: Wind, text: `Gusts ${f.max_gust_mph} mph` } : null,
    f.snowfall_in != null && f.snowfall_in >= 1 ? { icon: Snowflake, text: `${Math.round(f.snowfall_in)} in snow` } : null,
    f.min_wind_chill_f != null && f.min_wind_chill_f <= 20 ? { icon: Snowflake, text: `Wind chill ${f.min_wind_chill_f}°F` } : null,
    f.peak_smoke_aqi != null ? { icon: Haze, text: `Smoke AQI ${f.peak_smoke_aqi}` } : null,
  ].filter((c) => c !== null);

  return (
    <li className="flex gap-4 px-5 py-4">
      <ScoreChip score={score} level={score === null ? null : levelFor(score)} />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <Link href={`/sites/${b.site_id}`} className="font-medium text-ink hover:text-accent">
            {b.site_name}
          </Link>
          <span className="text-xs text-muted">
            {b.generated_by === "template" ? "Template" : "Gemini"} · {relativeTime(b.generated_at)}
          </span>
        </div>
        <p className="text-sm text-ink-2">{b.summary}</p>
        {(f.nws_alerts?.length ?? 0) > 0 && (
          <p className="text-xs text-[#ffd27a]">In force: {f.nws_alerts!.join(", ")}</p>
        )}
        {chips.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {chips.map((c) => (
              <li key={c.text} className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs text-ink-2">
                <c.icon className="h-3.5 w-3.5" aria-hidden />
                {c.text}
              </li>
            ))}
          </ul>
        )}
        {(f.recommendations?.length ?? 0) > 0 && (
          <ul className="list-disc pl-5 text-xs text-muted">
            {f.recommendations!.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}
