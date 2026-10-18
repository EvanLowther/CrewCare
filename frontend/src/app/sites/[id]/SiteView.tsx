"use client";

import {
  ArrowLeft,
  Bell,
  Check,
  CheckCircle2,
  CloudRain,
  CloudSun,
  Droplets,
  Haze,
  Layers,
  Lock,
  MapPin,
  OctagonAlert,
  Plus,
  Settings,
  ThermometerSun,
  TrendingUp,
  TriangleAlert,
  Umbrella,
  Wind,
  Zap,
  type LucideIcon,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useState } from "react";
import { HeatIndexChart, RainChanceChart, RiskHistoryChart } from "@/components/charts";
import { useMe } from "@/components/MeProvider";
import { ModelSwitch } from "@/components/ModelSwitch";
import { Card, CardHeader, EmptyState, ErrorBanner, PageBody, SeverityBadge } from "@/components/ui";
import { api, type Alert, type Conditions, type HazardReport, type RiskPoint, type Scorer, type SiteDetail } from "@/lib/api";
import { alertEndsAt, alertLabel, inForce, SEVERITY_RANK } from "@/lib/alerts";
import { alertKind, factorKind, HAZARD_KINDS, kindChipStyle } from "@/lib/hazardKinds";
import { relativeTime, round, siteHour, siteTime } from "@/lib/format";
import { HAZARD_LABELS, REPORT_SEVERITY_COLORS } from "@/lib/reports";
import { levelFor, RISK_COLORS, RISK_GUIDANCE, RISK_LABELS, RISK_TEXT } from "@/lib/risk";
import { useNow } from "@/lib/useNow";
import { usePolling } from "@/lib/usePolling";

// Leaflet needs `window`, so the map only renders in the browser.
const SiteMap = dynamic(() => import("@/components/SiteMap"), {
  ssr: false,
  loading: () => <div className="flex h-full items-center justify-center text-sm text-muted">Loading map…</div>,
});

const OTHER: Record<Scorer, Scorer> = { ml: "rules", rules: "ml" };
const SCORER_NAMES: Record<Scorer, string> = { ml: "Predictive", rules: "Real-time data" };

export function SiteView({ id, initialModel }: { id: string; initialModel: Scorer }) {
  const [model, setModel] = useState<Scorer>(initialModel);
  const { me } = useMe();
  const viewer = me?.user?.id ?? null;
  // Refetch when the viewer changes: their role decides what they may see and do here.
  const fetchSite = useCallback(() => api.site(Number(id), model), [id, model, viewer]); // eslint-disable-line react-hooks/exhaustive-deps
  const { data, error } = usePolling(fetchSite, 30_000);

  const notFound = error === "Site not found";
  const hidden = error === "You're not on this site";
  if (notFound || hidden) {
    return (
      <PageBody>
        <Card>
          <EmptyState
            icon={hidden ? Lock : MapPin}
            title={hidden ? "You're not on this site" : "Site not found"}
            detail={
              hidden
                ? me?.user
                  ? "It's a private site. Ask one of its managers to add you."
                  : "It's a private site. Sign in if you're one of its crew."
                : `There is no site with id ${id}.`
            }
          />
          <div className="pb-8 text-center">
            <Link href="/" className="text-sm text-accent hover:underline">
              Back to the dashboard
            </Link>
          </div>
        </Card>
      </PageBody>
    );
  }
  if (!data) {
    return <PageBody>{error ? <ErrorBanner message={error} retrying /> : <p className="text-sm text-muted">Loading site…</p>}</PageBody>;
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
  const { site, conditions, last_24h: last24, air_quality: air, forecast, alerts, reports, risk_history: history } = detail;
  const smokeAqi = air?.us_aqi_pm2_5 ?? null;
  const tz = site.timezone;
  const lightning = alerts.find((a) => a.type === "lightning" && a.all_clear_at);
  const risk = site.risk;
  const factors = risk?.factors ?? [];
  const now = useNow();
  const { role } = useMe();
  const canReport = !!site.my_role || role === "admin";
  const [resolved, setResolved] = useState<Set<string>>(new Set());
  const [resolveError, setResolveError] = useState<string | null>(null);
  const shownReports = reports.filter((r) => !resolved.has(r.id));

  // The other scorer's number, so the page always shows both (they can disagree; that's the point).
  const fetchOther = useCallback(() => api.site(site.id, OTHER[model]), [site.id, model]);
  const other = usePolling(fetchOther, 60_000).data?.site.risk ?? null;
  const topAction = factors.find((f) => f.action)?.action ?? other?.factors.find((f) => f.action)?.action ?? null;
  const actionWhy = factors.find((f) => f.action) ?? other?.factors.find((f) => f.action);

  // Nearby sites for the map, scored by the same model.
  const fetchSites = useCallback(() => api.sites(model), [model]);
  const nearby = usePolling(fetchSites, 60_000).data?.sites ?? [site];

  async function resolve(report: HazardReport) {
    setResolveError(null);
    try {
      await api.resolveReport(report.id);
      setResolved((prev) => new Set(prev).add(report.id));
    } catch (e) {
      setResolveError(e instanceof Error ? e.message : "Couldn't resolve the report");
    }
  }

  const glow = risk ? `radial-gradient(ellipse at 80% 0%, ${RISK_COLORS[risk.level]}22 0%, #0a0d13 55%)` : undefined;

  return (
    <main className="mx-auto flex w-full max-w-[1600px] flex-col gap-5 px-0 pb-10 sm:px-6 sm:pt-5">
      {error && (
        <div className="px-4 sm:px-0">
          <ErrorBanner message={error} retrying />
        </div>
      )}
      {lightning && <StopWorkBanner alert={lightning} timeZone={tz} />}

      <div className="flex flex-wrap gap-5">
        <section
          aria-label="Site summary"
          className="flex flex-[1_1_360px] flex-col gap-4 border-line px-4 pt-2 pb-2 sm:max-w-[460px] sm:rounded-2xl sm:border sm:p-5"
          style={{ background: glow }}
        >
          <div className="flex items-center justify-between gap-3">
            <Link href="/" className="flex min-h-11 items-center gap-1.5 text-sm text-accent">
              <ArrowLeft className="h-4 w-4" aria-hidden /> All sites
            </Link>
            <ModelSwitch value={model} onChange={onModelChange} />
          </div>

          <div className="flex flex-col gap-1.5">
            <p className="eyebrow">
              {[site.county ? `${site.county} County` : null, site.plant_type, site.capacity_mw ? `${Math.round(site.capacity_mw).toLocaleString()} MW` : null]
                .filter(Boolean)
                .join(" · ")}
            </p>
            <h1 className="font-display text-[44px] leading-[0.95] font-extrabold sm:text-[52px]">{site.name}</h1>
            <div className="flex flex-wrap items-center gap-2 text-[13px] text-ink-2">
              {site.utility}
              {!site.is_reference && (
                <span className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-xs">
                  <Lock className="h-3 w-3" aria-hidden /> Private site
                </span>
              )}
              {site.my_role && (
                <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs text-ink">
                  You: {site.my_role === "manager" ? "Manager" : "Crew"}
                </span>
              )}
            </div>
            {site.description && <p className="mt-1 text-sm whitespace-pre-line text-ink">{site.description}</p>}
          </div>

          {risk ? (
            <div className="flex items-end gap-4">
              <span
                className="font-display text-[112px] leading-[0.8] font-extrabold sm:text-[120px]"
                style={{ color: RISK_COLORS[risk.level], textShadow: `0 0 40px ${RISK_COLORS[risk.level]}73` }}
              >
                {risk.score.toFixed(1)}
              </span>
              <div className="flex flex-col gap-1.5 pb-1">
                <span className="font-mono text-xs font-medium tracking-[0.14em]" style={{ color: RISK_TEXT[risk.level] }}>
                  {RISK_LABELS[risk.level].toUpperCase()}
                </span>
                <span className="text-base leading-tight font-semibold">{RISK_GUIDANCE[risk.level]}</span>
                <span className="text-xs text-ink-2">
                  {SCORER_NAMES[model]} · out of 10 · {relativeTime(risk.updated_at, now)}
                </span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-ink-2">Getting live weather for this site: the first scores appear in about a minute.</p>
          )}

          <div className="grid grid-cols-2 overflow-hidden rounded-xl border border-line">
            {([model, OTHER[model]] as Scorer[]).map((s, i) => {
              const r = s === model ? risk : other;
              return (
                <div key={s} className={`flex flex-col gap-0.5 px-3 py-2.5 ${i === 0 ? "bg-[#ffffff08]" : "border-l border-line"}`}>
                  <span className="font-mono text-[10px] tracking-[0.1em] text-ink-2">{SCORER_NAMES[s].toUpperCase()}</span>
                  <span className="text-[15px] font-semibold">
                    {r ? (
                      <>
                        <span style={{ color: RISK_TEXT[r.level] }}>{r.score.toFixed(1)}</span> · {RISK_LABELS[r.level]}
                      </>
                    ) : (
                      <span className="text-muted">–</span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>

          <ScoreToday history={history} timeZone={tz} now={now} />

          <section aria-label="What's driving it" className="flex flex-col gap-2">
            <h2 className="text-xs font-semibold text-ink-2">What&apos;s driving it</h2>
            {factors.length === 0 ? (
              <p className="text-sm text-ink-2">Nothing notable right now.</p>
            ) : (
              factors.map((f) => {
                const max = Math.max(...factors.map((x) => x.contribution), 0.1);
                const color = risk ? RISK_COLORS[risk.level] : RISK_COLORS[levelFor(f.contribution)];
                const kind = factorKind(f.key, f.label);
                const KindIcon = HAZARD_KINDS[kind].icon;
                return (
                  <div key={f.key} className="grid grid-cols-[24px_minmax(0,1fr)_44px] items-center gap-2.5">
                    <span
                      className="flex h-6 w-6 items-center justify-center rounded-md"
                      style={kindChipStyle(kind)}
                      title={HAZARD_KINDS[kind].label}
                    >
                      <KindIcon className="h-3.5 w-3.5" aria-label={HAZARD_KINDS[kind].label} />
                    </span>
                    <div className="flex flex-col gap-1.5">
                      <span className="text-sm">{f.label}</span>
                      <span className="relative h-1 rounded-sm bg-line-soft">
                        <span className="absolute inset-y-0 left-0 rounded-sm" style={{ width: `${(f.contribution / max) * 100}%`, background: color }} />
                      </span>
                    </div>
                    <span className="text-right font-mono text-[13px]" style={{ color: risk ? RISK_TEXT[risk.level] : undefined }}>
                      +{f.contribution.toFixed(1)}
                    </span>
                  </div>
                );
              })
            )}
            {topAction && (
              <div className="mt-1 flex items-start gap-2.5 rounded-[10px] bg-[#0f1a24] px-3 py-2.5 text-[13px] leading-snug">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
                <span>
                  <strong className="font-semibold">{topAction}.</strong>{" "}
                  {actionWhy && <span className="text-ink-2">Because: {actionWhy.label}.</span>}
                </span>
              </div>
            )}
          </section>

          <NextHours conditions={conditions} forecast={forecast} timeZone={tz} />

          <div className="flex gap-2.5">
            <Link
              href={canReport ? `/report?site=${site.id}` : "/report"}
              className="flex min-h-12 flex-1 items-center justify-center gap-2 rounded-xl bg-accent-strong text-[15px] font-semibold text-on-accent hover:brightness-110"
            >
              <Plus className="h-[18px] w-[18px]" aria-hidden /> Report a hazard
            </Link>
            <Link
              href="/briefings"
              className="flex min-h-12 items-center justify-center rounded-xl border border-[#2a3446] px-4 text-[15px] text-ink hover:border-accent"
            >
              Crew brief
            </Link>
            {site.can_manage && (
              <Link
                href={`/sites/${site.id}/manage`}
                aria-label="Manage site"
                title="Manage site"
                className="flex min-h-12 w-12 items-center justify-center rounded-xl border border-[#2a3446] text-ink-2 hover:text-ink"
              >
                <Settings className="h-[18px] w-[18px]" aria-hidden />
              </Link>
            )}
          </div>
        </section>

        <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-5">
          <section
            aria-label="Site map"
            className="relative h-[300px] overflow-hidden border-y border-line-soft sm:h-[560px] sm:rounded-2xl sm:border"
          >
            <SiteMap
              sites={nearby}
              selectedId={site.id}
              model={model}
              reports={shownReports}
              alerts={alerts}
              focus={{ lat: site.latitude, lng: site.longitude, zoom: 8 }}
            />
          </section>

          <div className="grid gap-5 px-4 sm:grid-cols-2 sm:px-0">
            <Card>
              <CardHeader title="Active alerts" icon={Bell} subtitle="NWS warnings, nearby wildfires, earthquakes, smoke" />
              <SiteAlerts alerts={alerts} timeZone={tz} />
            </Card>
            <Card>
              <CardHeader
                title="Crew reports"
                icon={MapPin}
                subtitle="At this site or within 5 miles"
                actions={
                  canReport ? (
                    <Link href={`/report?site=${site.id}`} className="text-[13px] text-accent hover:underline">
                      Report a hazard
                    </Link>
                  ) : undefined
                }
              />
              {resolveError && <p className="mx-5 mb-3 rounded-lg bg-[rgb(255_74_74/0.12)] px-3 py-2 text-sm text-[#ff9b9b]">{resolveError}</p>}
              {shownReports.length === 0 ? (
                <QuietRow icon={<span className="mx-2.5 h-4 w-4 rotate-45 rounded-[3px] border-[1.5px] border-muted" />} title="No crew reports at this site" detail="Reports show on the map as diamonds for 24 h" />
              ) : (
                <ul className="divide-y divide-line border-t border-line">
                  {shownReports.map((r) => (
                    <li key={r.id} className="flex gap-3 px-5 py-3">
                      {r.photo_url ? (
                        // eslint-disable-next-line @next/next/no-img-element -- served by our API, sizes vary
                        <img src={api.photoUrl(r.photo_url)} alt="" className="h-14 w-14 shrink-0 rounded-lg object-cover" />
                      ) : (
                        <span className="flex h-14 w-14 shrink-0 items-center justify-center">
                          <span className="h-6 w-6 rotate-45 rounded-[4px]" style={{ background: REPORT_SEVERITY_COLORS[r.severity] }} />
                        </span>
                      )}
                      <div className="min-w-0 text-sm">
                        <p className="font-medium text-ink">
                          {HAZARD_LABELS[r.hazard_type]} · <span className="text-ink-2">{r.severity} severity</span>
                        </p>
                        {r.description && <p className="mt-0.5 text-ink-2">{r.description}</p>}
                        <p className="mt-1 text-xs text-muted">
                          {r.reporter_name ?? "Crew member"} · {relativeTime(r.created_at)} · {distanceLabel(site, r)}
                        </p>
                      </div>
                      {site.can_manage && r.site_id === site.id && (
                        <button
                          type="button"
                          onClick={() => resolve(r)}
                          title="Mark resolved: it leaves the map"
                          className="ml-auto inline-flex h-fit shrink-0 items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-xs text-ink-2 hover:text-ink"
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> Resolve
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-5 px-4 sm:px-0">
        <Card>
          <CardHeader
            title="Current conditions"
            icon={CloudSun}
            subtitle={conditions ? `As of ${siteTime(conditions.ts, tz)} local time` : "No weather reading yet"}
          />
          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-b-2xl border-t border-line bg-line sm:grid-cols-3 xl:grid-cols-9">
            <Metric icon={ThermometerSun} label="Heat index" value={round(conditions?.heat_index_f)} unit="°F" />
            <Metric icon={ThermometerSun} label="Temperature" value={round(conditions?.temp_f)} unit="°F" />
            <Metric icon={Droplets} label="Humidity" value={round(conditions?.humidity_pct)} unit="%" />
            <Metric icon={Wind} label="Wind / gusts" value={`${round(conditions?.wind_mph)} / ${round(conditions?.gust_mph)}`} unit="mph" />
            <Metric icon={CloudRain} label="Rain, last 24 h" value={round(last24?.total_precip_in, 2)} unit="in" />
            <Metric icon={Umbrella} label="Rain chance" value={round(conditions?.precip_prob_pct)} unit="%" />
            <Metric icon={Layers} label="Soil moisture" value={conditions?.soil_moisture == null ? "–" : Math.round(conditions.soil_moisture * 100).toString()} unit="%" />
            <Metric icon={Zap} label="Storm energy" value={conditions?.cape_jkg == null ? "–" : Math.round(conditions.cape_jkg).toLocaleString()} unit="J/kg" />
            <Metric icon={Haze} label="Air quality (smoke)" value={round(smokeAqi)} unit={`AQI · ${aqiCategory(smokeAqi)}`} />
          </div>
        </Card>

        <Card>
          <CardHeader title="Hazard index, past 24 h and next 24 h" icon={TrendingUp} subtitle="Solid: scored hours · dashed: forecast" />
          <div className="px-2 pb-4">
            {history.length > 0 ? (
              <RiskHistoryChart points={history} timeZone={tz} now={now} />
            ) : (
              <EmptyState icon={TrendingUp} title="No scores yet" detail="Scores are updated every 5 minutes; a new site gets its first ones in about a minute." />
            )}
          </div>
        </Card>

        <div className="grid gap-5 lg:grid-cols-2">
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
        <p className="font-mono text-[10px] tracking-[0.08em] text-muted">
          {risk ? `${risk.model_version.toUpperCase()} · ` : ""}UPDATED {siteTime(new Date(now).toISOString(), tz)} SITE TIME
        </p>
      </div>
    </main>
  );
}

/** Today's scored hours as thin bars, the latest on the right. */
function ScoreToday({ history, timeZone, now }: { history: RiskPoint[]; timeZone: string; now: number }) {
  const points = history
    .filter((p) => p.kind === "current" && new Date(p.ts).getTime() <= now)
    .sort((a, b) => a.ts.localeCompare(b.ts))
    .slice(-12);
  if (points.length === 0) return null;
  const hourLabel = (iso: string) => siteHour(iso, timeZone).replace(" AM", "a").replace(" PM", "p");
  return (
    <section aria-label="Score, last 12 scored hours" className="rounded-[14px] border border-line bg-[rgb(8_11_17/0.8)] px-3.5 pt-3.5 pb-2.5">
      <div className="mb-2.5 flex justify-between text-xs">
        <span className="font-semibold">Score, recent hours</span>
        <span className="eyebrow">Hourly · site time</span>
      </div>
      <div className="relative flex h-[104px] items-end justify-between gap-1.5 border-b border-line">
        <div className="absolute inset-x-0 bottom-[75%] border-t border-dashed border-[#3a2226]" aria-hidden />
        {points.map((p) => {
          const color = RISK_COLORS[levelFor(p.score)];
          return (
            <div key={p.ts} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
              <span className="font-mono text-[9px] text-ink-2">{p.score.toFixed(1)}</span>
              <div className="w-[3px] rounded-sm" style={{ height: `${p.score * 8}px`, background: color, boxShadow: `0 0 8px ${color}` }} />
            </div>
          );
        })}
      </div>
      <div className="flex justify-between gap-1.5 pt-1.5">
        {points.map((p) => (
          <span key={p.ts} className="flex-1 text-center font-mono text-[9px] text-muted">
            {hourLabel(p.ts)}
          </span>
        ))}
      </div>
    </section>
  );
}

/** Four tiles from the next 24 h of forecast: the heaviest rain hour, the strongest gust, the peak heat index, now. */
function NextHours({ conditions, forecast, timeZone }: { conditions: Conditions | null; forecast: Conditions[]; timeZone: string }) {
  const next = forecast.slice(0, 24);
  const peak = (key: "precip_in" | "gust_mph" | "heat_index_f") =>
    next.reduce<Conditions | null>((best, c) => (c[key] !== null && (best === null || (c[key] ?? 0) > (best[key] ?? 0)) ? c : best), null);
  const rain = peak("precip_in");
  const gust = peak("gust_mph");
  const heat = peak("heat_index_f");
  const hour = (c: Conditions) => siteHour(c.ts, timeZone);
  const tiles = [
    rain && (rain.precip_in ?? 0) >= 0.01
      ? { t: hour(rain), v: `${round(rain.precip_in, 1)} in`, d: `rain${rain.precip_prob_pct !== null ? ` · ${Math.round(rain.precip_prob_pct)}%` : ""}` }
      : { t: "24 H", v: "Dry", d: "no rain forecast" },
    gust ? { t: hour(gust), v: `${round(gust.gust_mph)} mph`, d: "peak gusts" } : null,
    heat ? { t: hour(heat), v: `${round(heat.heat_index_f)}°F`, d: "peak heat index" } : null,
    { t: "NOW", v: `${round(conditions?.heat_index_f)}°F`, d: "heat index" },
  ].filter((x): x is { t: string; v: string; d: string } => x !== null);
  if (next.length === 0) return null;
  return (
    <section aria-label="Next 24 hours" className="grid grid-cols-4 overflow-hidden rounded-xl border border-line">
      {tiles.map((x) => (
        <div key={x.d} className="flex flex-col gap-0.5 border-r border-line-soft p-2.5 last:border-r-0">
          <span className="font-mono text-[10px] text-muted">{x.t}</span>
          <span className="text-[15px] font-semibold">{x.v}</span>
          <span className="text-[11px] text-ink-2">{x.d}</span>
        </div>
      ))}
    </section>
  );
}

function QuietRow({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return (
    <div className="mx-5 mb-5 flex items-center gap-3 rounded-xl border border-dashed border-line p-3.5">
      {icon}
      <span className="flex flex-col gap-0.5">
        <span className="text-sm">{title}</span>
        <span className="text-xs text-ink-2">{detail}</span>
      </span>
    </div>
  );
}

/** EPA AQI category (PM2.5); the Real-time score counts smoke from 101 and Cal/OSHA requires N95s from 151. */
function aqiCategory(aqi: number | null): string {
  if (aqi == null) return "";
  if (aqi > 300) return "hazardous";
  if (aqi > 200) return "very unhealthy";
  if (aqi > 150) return "unhealthy";
  if (aqi > 100) return "sensitive groups";
  if (aqi > 50) return "moderate";
  return "good";
}

function Metric({ icon: Icon, label, value, unit }: { icon: LucideIcon; label: string; value: string; unit: string }) {
  return (
    <div className="bg-card px-4 py-4">
      <p className="flex items-center gap-1.5 truncate text-xs whitespace-nowrap text-muted">
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

function SiteAlerts({ alerts: all, timeZone }: { alerts: Alert[]; timeZone: string }) {
  const now = useNow(15_000);
  const alerts = all.filter((a) => inForce(a, now));
  if (alerts.length === 0) {
    return (
      <QuietRow
        icon={
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#10201a] text-risk-low">
            <Check className="h-[18px] w-[18px]" aria-hidden />
          </span>
        }
        title="No active alerts"
        detail="No NWS warnings, nearby wildfires or felt earthquakes"
      />
    );
  }
  const sorted = [...alerts].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]);
  return (
    <ul className="divide-y divide-line border-t border-line">
      {sorted.map((a) => {
        const kind = alertKind(a);
        const Icon = HAZARD_KINDS[kind].icon;
        const ends = alertEndsAt(a);
        return (
          <li key={a.id} className="flex gap-3 px-5 py-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg" style={kindChipStyle(kind)}>
              <Icon className="h-4 w-4" aria-hidden />
            </span>
            <div className="min-w-0 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-ink">{alertLabel(a)}</span>
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
  if (left === 0) return null; // all clear: gone at 0:00, not stuck there until the next refresh
  const mm = Math.floor(left / 60_000);
  const ss = Math.floor((left % 60_000) / 1000).toString().padStart(2, "0");
  const meta = alert.meta as { strike_count?: number; nearest_strike_mi?: number };

  return (
    <div className="px-4 pt-4 sm:px-0 sm:pt-0">
      <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-[rgb(255_74_74/0.5)] bg-[rgb(255_74_74/0.14)] px-5 py-4">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-risk-extreme text-on-accent">
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
          <p className="tabular font-display text-4xl font-extrabold text-ink">
            {mm}:{ss}
          </p>
          <p className="text-xs text-muted">until all clear</p>
        </div>
      </div>
    </div>
  );
}

/** "0.4 mi from the site" / "800 ft from the site", great-circle distance from the site to the report pin. */
function distanceLabel(site: { latitude: number; longitude: number }, r: { latitude: number; longitude: number }) {
  const rad = Math.PI / 180;
  const dLat = (r.latitude - site.latitude) * rad;
  const dLng = (r.longitude - site.longitude) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(site.latitude * rad) * Math.cos(r.latitude * rad) * Math.sin(dLng / 2) ** 2;
  const mi = 3958.8 * 2 * Math.asin(Math.sqrt(h));
  return mi < 0.2 ? `${Math.round(mi * 5280)} ft from the site` : `${mi.toFixed(1)} mi from the site`;
}
