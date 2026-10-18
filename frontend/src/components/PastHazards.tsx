"use client";

import { History, MapPin } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type LocationHistory, type PastReport, type PastStormEvent } from "@/lib/api";
import { eventKind, HAZARD_KINDS, kindChipStyle } from "@/lib/hazardKinds";
import { HAZARD_LABELS } from "@/lib/reports";
import { Card, CardHeader } from "./ui";

// "A database of location hazards for future project owners": what crews reported near a place (resolved and
// expired too) and what NOAA recorded near it, so a manager sees a spot's track record before work starts.

const SHOWN = 8;

const STATUS_LABELS: Record<PastReport["status"], string> = { active: "Active", resolved: "Resolved", expired: "Expired" };

function date(iso: string): string {
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function dollars(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${n}`;
}

/** Past hazards for a site (its page) or a spot (the new-site form, refetched as the pin moves). */
export function PastHazards(props: { siteId: number } | { point: { lat: number; lng: number } | null }) {
  const siteId = "siteId" in props ? props.siteId : null;
  const point = "point" in props ? props.point : null;
  const [history, setHistory] = useState<LocationHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const lat = point?.lat;
  const lng = point?.lng;
  useEffect(() => {
    if (siteId === null && (lat === undefined || lng === undefined)) return;
    let cancelled = false;
    // Wait for the pin to settle before asking (dragging fires many moves).
    const timer = setTimeout(
      async () => {
        setLoading(true);
        try {
          const h = siteId !== null ? await api.siteHistory(siteId) : await api.placeHistory(lat!, lng!);
          if (!cancelled) {
            setHistory(h);
            setError(null);
          }
        } catch (e) {
          if (!cancelled) setError(e instanceof Error ? e.message : "Couldn't load past hazards");
        } finally {
          if (!cancelled) setLoading(false);
        }
      },
      siteId !== null ? 0 : 600,
    );
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [siteId, lat, lng]);

  const forSite = siteId !== null;
  return (
    <Card>
      <CardHeader
        title={forSite ? "Past hazards here" : "Past hazards at this spot"}
        icon={History}
        subtitle={
          history
            ? `Crew reports within ${history.report_radius_mi} mi · NOAA storm events within ${history.storm_radius_mi} mi, ${history.storm_years}`
            : "Crew reports within 5 mi and NOAA storm events within 25 mi"
        }
      />
      <div className="flex flex-col gap-5 px-5 pb-5">
        {!forSite && !point ? (
          <p className="text-sm text-muted">Put the pin on the map to see what happened near it before.</p>
        ) : error ? (
          <p className="text-sm text-[#ff9b9b]">{error}</p>
        ) : !history ? (
          <p className="text-sm text-muted">Looking up past hazards…</p>
        ) : (
          <div className={`flex flex-col gap-5 transition-opacity ${loading ? "opacity-60" : ""}`}>
            <Reports reports={history.reports} radius={history.report_radius_mi} />
            <StormEvents history={history} />
          </div>
        )}
      </div>
    </Card>
  );
}

function Reports({ reports, radius }: { reports: PastReport[]; radius: number }) {
  const [all, setAll] = useState(false);
  return (
    <section aria-label="Past crew reports" className="flex flex-col gap-2">
      <h3 className="text-xs font-semibold text-ink-2">
        Crew reports <span className="font-normal text-muted">· {reports.length === 50 ? "latest 50" : reports.length}</span>
      </h3>
      {reports.length === 0 ? (
        <p className="text-sm text-muted">No crew reports within {radius} mi yet.</p>
      ) : (
        <ul className="divide-y divide-line rounded-xl border border-line">
          {(all ? reports : reports.slice(0, SHOWN)).map((r) => (
            <li key={r.id} className="flex gap-3 px-3 py-2.5 text-sm">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-ink">
                  {HAZARD_LABELS[r.hazard_type]} <span className="text-muted">· {r.severity}</span>
                </p>
                {r.description && <p className="line-clamp-2 text-xs text-ink-2">{r.description}</p>}
                <p className="text-xs text-muted">
                  {date(r.created_at)} · {r.distance_mi} mi away{r.site_name ? ` · ${r.site_name}` : ""}
                </p>
              </div>
              <span className={`h-fit shrink-0 rounded-full px-2 py-0.5 text-[11px] ${r.status === "active" ? "bg-accent-soft text-accent" : "bg-line-soft text-muted"}`}>
                {STATUS_LABELS[r.status]}
              </span>
            </li>
          ))}
        </ul>
      )}
      {reports.length > SHOWN && (
        <button type="button" onClick={() => setAll((a) => !a)} className="self-start text-xs text-accent hover:underline">
          {all ? "Show fewer" : `Show all ${reports.length}`}
        </button>
      )}
    </section>
  );
}

function StormEvents({ history }: { history: LocationHistory }) {
  const [all, setAll] = useState(false);
  const events = history.storm_events;
  return (
    <section aria-label="NOAA storm events" className="flex flex-col gap-2">
      <h3 className="text-xs font-semibold text-ink-2">
        NOAA storm events <span className="font-normal text-muted">· {history.storm_event_count}</span>
      </h3>
      {history.storm_event_count === 0 ? (
        <p className="text-sm text-muted">
          None recorded within {history.storm_radius_mi} mi in {history.storm_years}. (Events NOAA logs by county or zone,
          with no exact spot, aren&apos;t counted.)
        </p>
      ) : (
        <>
          <ul className="flex flex-wrap gap-1.5" aria-label="By type">
            {history.storm_event_types.slice(0, 8).map((t) => {
              const kind = eventKind(t.event_type);
              const Icon = HAZARD_KINDS[kind].icon;
              return (
                <li key={t.event_type} className="flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs text-ink-2">
                  <Icon className="h-3.5 w-3.5" style={{ color: HAZARD_KINDS[kind].color }} aria-hidden />
                  {t.event_type} <span className="font-mono text-muted">{t.count}</span>
                </li>
              );
            })}
          </ul>
          <ul className="divide-y divide-line rounded-xl border border-line">
            {(all ? events : events.slice(0, SHOWN)).map((e) => (
              <StormEventRow key={e.event_id} e={e} />
            ))}
          </ul>
          {events.length > SHOWN && (
            <button type="button" onClick={() => setAll((a) => !a)} className="self-start text-xs text-accent hover:underline">
              {all ? "Show fewer" : `Show the latest ${events.length}`}
            </button>
          )}
        </>
      )}
    </section>
  );
}

function StormEventRow({ e }: { e: PastStormEvent }) {
  const kind = eventKind(e.event_type);
  const Icon = HAZARD_KINDS[kind].icon;
  const harm = [
    e.deaths ? `${e.deaths} death${e.deaths === 1 ? "" : "s"}` : null,
    e.injuries ? `${e.injuries} injur${e.injuries === 1 ? "y" : "ies"}` : null,
    e.damage_usd ? `${dollars(e.damage_usd)} damage` : null,
  ].filter(Boolean);
  return (
    <li className="flex gap-3 px-3 py-2.5 text-sm">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md" style={kindChipStyle(kind)}>
        <Icon className="h-3.5 w-3.5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-ink">{e.event_type}</p>
        <p className="text-xs text-muted">
          {date(e.begin_ts)} · {e.distance_mi} mi away{e.place ? ` · ${e.place}` : ""}
        </p>
        {harm.length > 0 && <p className="text-xs text-[#ffd27a]">{harm.join(" · ")}</p>}
      </div>
    </li>
  );
}
