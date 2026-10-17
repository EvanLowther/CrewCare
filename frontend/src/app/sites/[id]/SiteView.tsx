"use client";

import {
  ArrowLeft,
  Bell,
  ClipboardCheck,
  CloudRain,
  CloudSun,
  Droplets,
  Gauge,
  Layers,
  MapPin,
  OctagonAlert,
  ThermometerSun,
  TrendingUp,
  Umbrella,
  Wind,
  Zap,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { RainChanceChart, HeatIndexChart, RiskHistoryChart } from "@/components/charts";
import { RiskGauge } from "@/components/RiskGauge";
import { Card, CardHeader, EmptyState, ErrorBanner, LiveIndicator, ScoreChip, SeverityBadge } from "@/components/ui";
import { ModelSwitch } from "@/components/ModelSwitch";
import { api, type Alert, type Scorer, type SiteDetail } from "@/lib/api";
import { ALERT_ICONS, ALERT_LABELS, SEVERITY_RANK } from "@/lib/alerts";
import { relativeTime, round, siteTime } from "@/lib/format";
import { HAZARD_LABELS } from "@/lib/reports";
import { levelFor, RISK_COLORS } from "@/lib/risk";
import { useNow } from "@/lib/useNow";
import { usePolling } from "@/lib/usePolling";

export function SiteView({ id, initialModel }: { id: string; initialModel: Scorer }) {
  const [model, setModel] = useState<Scorer>(initialModel);
  const fetchSite = useCallback(() => api.site(Number(id), model), [id, model]);
  const { data, error } = usePolling(fetchSite, 30_000);

  if (error?.startsWith("404")) {
    return (
      <Card>
        <EmptyState icon={MapPin} title="Site not found" detail={`There is no site with id ${id}.`} />
        <div className="pb-8 text-center">
          <Link href="/" className="text-sm text-accent hover:underline">
            Back to the dashboard
          </Link>
        </div>
      </Card>
    );
  }
  if (!data) {
    return error ? <ErrorBanner message={error} /> : <p className="text-sm text-muted">Loading site…</p>;
  }
  return <SiteDetailView detail={data} error={error} model={model} onModelChange={setModel} />;
}

function SiteDetailView({
  detail,
  error,
  model,
  onModelChange,
}: {
  detail: SiteDetail;
  error: string | null;
  model: Scorer;
  onModelChange: (next: Scorer) => void;
}) {
  const { site, conditions, last_24h: last24, forecast, alerts, reports, risk_history: history } = detail;
  const tz = site.timezone;
  const lightning = alerts.find((a) => a.type === "lightning" && a.all_clear_at);
  const factors = site.risk?.factors ?? [];
  const topAction = factors.find((f) => f.action)?.action ?? null;
  const now = useNow();

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link href="/" className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Dashboard
        </Link>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight text-ink">{site.name}</h1>
            <p className="mt-1 text-sm text-ink-2">
              {[site.utility, `${site.county} County`, site.plant_type, site.capacity_mw ? `${Math.round(site.capacity_mw).toLocaleString()} MW` : null]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <ModelSwitch value={model} onChange={onModelChange} />
            <LiveIndicator label={`Local time ${siteTime(new Date(now).toISOString(), tz)}`} />
            <ScoreChip score={site.risk?.score ?? null} level={site.risk?.level ?? null} size="lg" />
          </div>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      {lightning && <StopWorkBanner alert={lightning} timeZone={tz} />}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <Card>
          <CardHeader
            title="Hazard index"
            icon={Gauge}
            subtitle={site.risk ? `Updated ${relativeTime(site.risk.updated_at)} · ${site.risk.model_version}` : "Waiting for the first score"}
          />
          <div className="px-5 pb-5">
            <RiskGauge score={site.risk?.score ?? null} level={site.risk?.level ?? null} />
            {topAction && (
              <div className="mt-4 flex gap-2.5 rounded-lg border border-line bg-raised px-3.5 py-3 text-sm">
                <ClipboardCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
                <div>
                  <p className="text-xs text-muted">Recommended action</p>
                  <p className="text-ink">{topAction}</p>
                </div>
              </div>
            )}
            <h3 className="mt-5 text-xs font-medium text-muted">
              {model === "rules"
                ? "What's driving the score (each hazard out of 10)"
                : "What's driving the score (share of the model's score)"}
            </h3>
            {factors.length === 0 ? (
              <p className="mt-2 text-sm text-ink-2">Nothing notable right now.</p>
            ) : (
              <ul className="mt-2 divide-y divide-line">
                {factors.map((f) => (
                  <li key={f.key} className="py-2.5">
                    <div className="flex items-start justify-between gap-3 text-sm">
                      <span className="text-ink">{f.label}</span>
                      <span className="tabular shrink-0 text-ink-2">{f.contribution.toFixed(1)}</span>
                    </div>
                    <div className="mt-1.5 h-1.5 rounded-full bg-accent-soft">
                      <div
                        className="h-1.5 rounded-full"
                        style={{
                          width: `${Math.min(100, f.contribution * 10)}%`,
                          background: RISK_COLORS[levelFor(f.contribution)],
                        }}
                      />
                    </div>
                    {f.action && <p className="mt-1.5 text-xs text-muted">{f.action}</p>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Current conditions"
            icon={CloudSun}
            subtitle={conditions ? `As of ${siteTime(conditions.ts, tz)} local time` : "No weather reading yet"}
          />
          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-b-xl border-t border-line bg-line sm:grid-cols-4 lg:grid-cols-2 2xl:grid-cols-4">
            <Metric icon={ThermometerSun} label="Heat index" value={round(conditions?.heat_index_f)} unit="°F" />
            <Metric icon={ThermometerSun} label="Temperature" value={round(conditions?.temp_f)} unit="°F" />
            <Metric icon={Droplets} label="Humidity" value={round(conditions?.humidity_pct)} unit="%" />
            <Metric icon={Wind} label="Wind / gusts" value={`${round(conditions?.wind_mph)} / ${round(conditions?.gust_mph)}`} unit="mph" />
            <Metric icon={CloudRain} label="Rain, last 24 h" value={round(last24?.total_precip_in, 2)} unit="in" />
            <Metric icon={Umbrella} label="Rain chance" value={round(conditions?.precip_prob_pct)} unit="%" />
            <Metric icon={Layers} label="Soil moisture" value={conditions?.soil_moisture == null ? "–" : Math.round(conditions.soil_moisture * 100).toString()} unit="%" />
            <Metric icon={Zap} label="Storm energy" value={conditions?.cape_jkg == null ? "–" : Math.round(conditions.cape_jkg).toLocaleString()} unit="J/kg" />
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Hazard index, past 24 h and next 24 h" icon={TrendingUp} subtitle="Solid: scored hours · dashed: forecast" />
        <div className="px-2 pb-4">
          {history.length > 0 ? (
            <RiskHistoryChart points={history} timeZone={tz} now={now} />
          ) : (
            <EmptyState icon={TrendingUp} title="No scores yet" detail="The scoring job runs every 5 minutes." />
          )}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Heat index, next 48 h" icon={ThermometerSun} subtitle="Site-local time" />
          <div className="px-2 pb-4">
            {forecast.length > 0 ? <HeatIndexChart forecast={forecast} timeZone={tz} /> : <EmptyState icon={ThermometerSun} title="No forecast yet" />}
          </div>
        </Card>
        <Card>
          <CardHeader title="Chance of rain, next 48 h" icon={Umbrella} subtitle="Hourly" />
          <div className="px-2 pb-4">
            {forecast.length > 0 ? <RainChanceChart forecast={forecast} timeZone={tz} /> : <EmptyState icon={Umbrella} title="No forecast yet" />}
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Active alerts" icon={Bell} subtitle={`${alerts.length} at this site`} />
          <SiteAlerts alerts={alerts} timeZone={tz} />
        </Card>
        <Card>
          <CardHeader title="Crew reports within 5 miles" icon={MapPin} subtitle="Hazards pinned by field crews" />
          {reports.length === 0 ? (
            <EmptyState icon={MapPin} title="No crew reports nearby" detail="Reports from the field show up here with their photo." />
          ) : (
            <ul className="divide-y divide-line border-t border-line">
              {reports.map((r) => (
                <li key={r.id} className="flex gap-3 px-5 py-3">
                  {r.photo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element -- served by our API, sizes vary
                    <img src={api.photoUrl(r.photo_url)} alt="" className="h-14 w-14 shrink-0 rounded-lg object-cover" />
                  ) : (
                    <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
                      <MapPin className="h-5 w-5" aria-hidden />
                    </span>
                  )}
                  <div className="min-w-0 text-sm">
                    <p className="font-medium text-ink">
                      {HAZARD_LABELS[r.hazard_type]} · <span className="text-ink-2">{r.severity} severity</span>
                    </p>
                    {r.description && <p className="mt-0.5 text-ink-2">{r.description}</p>}
                    <p className="mt-1 text-xs text-muted">
                      {r.reporter_name ?? "Crew member"} · {relativeTime(r.created_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function Metric({ icon: Icon, label, value, unit }: { icon: LucideIcon; label: string; value: string; unit: string }) {
  return (
    <div className="bg-card px-4 py-4">
      <p className="flex items-center gap-1.5 truncate whitespace-nowrap text-xs text-muted">
        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
        {label}
      </p>
      <p className="mt-2 text-xl font-semibold text-ink">
        {value}
        {value !== "–" && <span className="ml-1 text-xs font-normal text-muted">{unit}</span>}
      </p>
    </div>
  );
}

function SiteAlerts({ alerts, timeZone }: { alerts: Alert[]; timeZone: string }) {
  if (alerts.length === 0) {
    return <EmptyState icon={Bell} title="No active alerts" detail="NWS warnings and stop-work alerts for this site show up here." />;
  }
  const sorted = [...alerts].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]);
  return (
    <ul className="divide-y divide-line border-t border-line">
      {sorted.map((a) => {
        const Icon = ALERT_ICONS[a.type];
        const ends = a.all_clear_at ?? (a.meta as { ends?: string | null }).ends ?? null;
        return (
          <li key={a.id} className="flex gap-3 px-5 py-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
              <Icon className="h-4 w-4" aria-hidden />
            </span>
            <div className="min-w-0 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-ink">{ALERT_LABELS[a.type]}</span>
                <SeverityBadge severity={a.severity} />
              </div>
              <p className="mt-1 text-ink-2">{a.message}</p>
              <p className="mt-1 text-xs text-muted">
                Since {siteTime(a.started_at, timeZone)}
                {ends && ` · until ${siteTime(ends, timeZone)} (${relativeTime(ends)})`}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Red banner with a live countdown to the lightning all-clear; each new strike moves all_clear_at later. */
function StopWorkBanner({ alert, timeZone }: { alert: Alert; timeZone: string }) {
  const now = useNow(1000);
  const left = Math.max(0, new Date(alert.all_clear_at!).getTime() - now);
  const mm = Math.floor(left / 60_000);
  const ss = Math.floor((left % 60_000) / 1000).toString().padStart(2, "0");
  const meta = alert.meta as { strike_count?: number; nearest_strike_mi?: number };

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-xl border border-[rgb(208_59_59/0.5)] bg-[rgb(208_59_59/0.14)] px-5 py-4">
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-risk-extreme text-white">
        <OctagonAlert className="h-5 w-5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-[#ffb3b3]">{alert.title}</p>
        <p className="text-sm text-ink-2">
          {meta.strike_count ? `${meta.strike_count} strikes` : "Lightning"}
          {meta.nearest_strike_mi ? `, nearest ${meta.nearest_strike_mi} mi` : ""} · all clear at{" "}
          {siteTime(alert.all_clear_at!, timeZone)} if no new strikes
        </p>
      </div>
      <div className="text-right">
        <p className="tabular text-3xl font-semibold text-ink">
          {mm}:{ss}
        </p>
        <p className="text-xs text-muted">until all clear</p>
      </div>
    </div>
  );
}
