"use client";

import { ArrowRight } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useState, useSyncExternalStore } from "react";
import { api, type Scorer, type SiteSummary } from "@/lib/api";
import { RISK_COLORS, RISK_LABELS, RISK_LEVELS, RISK_TEXT } from "@/lib/risk";
import { usePolling } from "@/lib/usePolling";
import { useSiteScope } from "@/lib/useSiteScope";
import { useMe } from "./MeProvider";
import { ModelSwitch } from "./ModelSwitch";
import { ScopeSwitch } from "./ScopeSwitch";
import type { MapInsets } from "./SiteMap";
import { SiteSearch } from "./TopNav";
import { ErrorBanner } from "./ui";

// Leaflet needs `window`, so the map only renders in the browser.
const SiteMap = dynamic(() => import("./SiteMap"), {
  ssr: false,
  loading: () => <div className="flex h-full items-center justify-center text-sm text-muted">Loading map…</div>,
});

const POLL_MS = 10_000;
const fetchAlerts = () => api.alerts();
const fetchReports = () => api.reports();

// On wide screens the panels float over the map; the first fit keeps sites out from under them.
const DESKTOP = "(min-width: 1024px)";
const DESKTOP_INSETS: MapInsets = { top: 60, right: 60, bottom: 120, left: 400 };
const NO_INSETS: MapInsets = { top: 56, right: 0, bottom: 40, left: 0 };
function subscribeDesktop(cb: () => void) {
  const mq = window.matchMedia(DESKTOP);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}
const isDesktop = () => window.matchMedia(DESKTOP).matches;

const PANEL = "rounded-2xl border border-line bg-panel backdrop-blur";

export function Dashboard() {
  const [model, setModel] = useState<Scorer>("rules"); // Real-time data first on every load
  const { me } = useMe();
  const scope = useSiteScope();
  const desktop = useSyncExternalStore(subscribeDesktop, isDesktop, () => true);
  // Refetch when the viewer changes (signing in reveals their private sites).
  const viewer = me?.user?.id ?? null;
  const fetchSites = useCallback(() => api.sites(model), [model, viewer]); // eslint-disable-line react-hooks/exhaustive-deps
  const sitesPoll = usePolling(fetchSites, POLL_MS);
  const alertsPoll = usePolling(fetchAlerts, POLL_MS);
  const reportsPoll = usePolling(fetchReports, POLL_MS);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const sites = (sitesPoll.data?.sites ?? []).filter((s) => scope.includes(s.id));
  const alerts = (alertsPoll.data?.alerts ?? []).filter((a) => scope.includes(a.site_id));
  const reports = (reportsPoll.data?.reports ?? []).filter((r) => r.site_id === null || scope.includes(r.site_id));
  const error = sitesPoll.error ?? alertsPoll.error;

  return (
    <main className="flex flex-col lg:relative lg:block lg:h-[calc(100dvh-61px)] lg:min-h-[700px] lg:overflow-hidden">
      {/* On phones this is just a wrapper (its children stack in page order); on desktop it's the left panel. */}
      <aside
        className={`contents lg:absolute lg:top-5 lg:bottom-5 lg:left-5 lg:z-[1001] lg:flex lg:w-[380px] lg:flex-col lg:gap-4 lg:overflow-hidden lg:p-5 ${PANEL} max-lg:border-0 max-lg:bg-transparent`}
      >
        <section className="order-1 flex flex-col gap-3.5 px-4 pt-6 pb-5 lg:p-0">
          <p className="eyebrow">{sites.length || 160} job sites · scored every 5 min</p>
          <h1 className="font-display text-[44px] leading-[0.92] font-extrabold lg:text-[50px]">
            The forecast your crew <span className="text-accent">actually</span> needs.
          </h1>
          <p className="text-sm leading-relaxed text-ink-2">
            Every site scored 0 to 10 for crew hazard. <strong className="font-semibold text-ink">Real-time</strong>:
            live NWS weather, smoke, nearby wildfires, earthquakes and warnings against OSHA and NWS work rules.{" "}
            <strong className="font-semibold text-ink">Predictive</strong>: our model&apos;s odds of a recorded hazard
            day, never below an active warning.
          </p>
          <ModelSwitch value={model} onChange={setModel} full />
          {error && <ErrorBanner message={error} />}
        </section>

        <section aria-label="Highest risk first" className="order-4 mx-4 mt-3 flex min-h-0 flex-col rounded-2xl border border-line bg-card lg:m-0 lg:flex-1 lg:rounded-none lg:border-0 lg:border-t lg:border-line-soft lg:bg-transparent">
          <div className="flex items-baseline justify-between px-3.5 pt-3.5 pb-2 lg:px-0 lg:pt-3">
            <h2 className="text-sm font-semibold">Highest risk first</h2>
            <span className="eyebrow">{model === "ml" ? "Predictive" : "Real-time"}</span>
          </div>
          <RankedList sites={sites} selectedId={selectedId} onSelect={setSelectedId} model={model} loading={!sitesPoll.data} />
        </section>
      </aside>

      <section
        aria-label="Site map"
        className="relative order-2 h-[60vh] max-h-[560px] min-h-[340px] overflow-hidden border-y border-line-soft lg:absolute lg:inset-0 lg:h-auto lg:max-h-none lg:border-0"
      >
        <SiteMap
          sites={sites}
          selectedId={selectedId}
          onSelect={setSelectedId}
          model={model}
          reports={reports}
          alerts={alerts}
          insets={desktop ? DESKTOP_INSETS : NO_INSETS}
          zoomPosition="bottomright"
        />
        <div className="absolute top-2.5 right-2.5 left-2.5 z-[1001] flex items-center gap-2 lg:top-5 lg:right-auto lg:left-[420px] lg:rounded-full lg:border lg:border-line lg:bg-panel lg:py-1.5 lg:pr-2 lg:pl-4">
          <span className="eyebrow hidden lg:inline">Scope</span>
          {scope.available ? (
            <ScopeSwitch value={scope.scope} onChange={scope.setScope} />
          ) : (
            <span className="hidden text-[13px] font-semibold lg:inline">All sites</span>
          )}
          <SiteSearch className="flex-1 max-lg:rounded-full max-lg:border max-lg:border-line max-lg:bg-panel lg:w-52 lg:flex-none" />
        </div>
        <Legend />
      </section>

      <div className="order-3 flex flex-wrap gap-3 px-4 pt-3.5 lg:absolute lg:right-[76px] lg:bottom-5 lg:left-[420px] lg:z-[1001] lg:gap-3.5 lg:p-0">
        <Totals sites={sites} alerts={alerts} loaded={!!sitesPoll.data && !!alertsPoll.data} />
      </div>

      <footer className="order-5 px-4 pt-6 pb-8 font-mono text-[10px] leading-relaxed tracking-[0.08em] text-muted lg:hidden">
        MODEL xgb-2026-10-17-us · DATA EIA-860M, NOAA, NWS, OPEN-METEO, NIFC, USGS
      </footer>
    </main>
  );
}

function RankedList({
  sites,
  selectedId,
  onSelect,
  model,
  loading,
}: {
  sites: SiteSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  model: Scorer;
  loading: boolean;
}) {
  const [all, setAll] = useState(false);
  const shown = all ? sites : sites.slice(0, 6);
  if (loading) return <p className="px-3.5 pb-4 text-sm text-muted lg:px-0">Loading sites…</p>;
  return (
    <>
      <ol className="flex min-h-0 flex-col overflow-y-auto lg:-mx-2">
        {shown.map((site, i) => {
          const risk = site.risk;
          const selected = site.id === selectedId;
          const color = risk ? RISK_COLORS[risk.level] : "#4a5368";
          return (
            <li key={site.id} className={`border-t border-line-soft lg:border-0 ${selected ? "bg-[#141b27] lg:rounded-lg" : ""}`}>
              <button
                type="button"
                onClick={() => onSelect(site.id)}
                aria-current={selected ? "true" : undefined}
                className="grid min-h-14 w-full grid-cols-[22px_minmax(0,1fr)_54px] items-center gap-2.5 px-3.5 py-2 text-left hover:bg-raised lg:rounded-lg lg:px-2"
              >
                <span className="font-mono text-[11px] text-muted">{String(i + 1).padStart(2, "0")}</span>
                <span className="flex min-w-0 flex-col gap-[3px]">
                  <span className="truncate text-sm font-medium">{site.name}</span>
                  <span className="truncate text-xs text-muted">
                    {[risk?.factors[0]?.label, site.county].filter(Boolean).join(" · ")}
                  </span>
                  <span className="relative h-[3px] overflow-hidden rounded-sm bg-line-soft">
                    <span className="absolute inset-y-0 left-0" style={{ width: `${(risk?.score ?? 0) * 10}%`, background: color }} />
                  </span>
                </span>
                <span className="flex flex-col items-end gap-0.5">
                  <span className="font-display text-2xl leading-none font-extrabold" style={{ color }}>
                    {risk ? risk.score.toFixed(1) : "–"}
                  </span>
                  <span className="font-mono text-[9px] tracking-[0.08em] text-ink-2">
                    {risk ? RISK_LABELS[risk.level].toUpperCase() : "NO SCORE"}
                  </span>
                </span>
              </button>
              {selected && (
                <Link
                  href={`/sites/${site.id}?model=${model}`}
                  className="flex items-center gap-1.5 px-3.5 pb-2.5 pl-[46px] text-[13px] font-semibold lg:px-2 lg:pl-[42px]"
                >
                  Open site page <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                </Link>
              )}
            </li>
          );
        })}
      </ol>
      {sites.length > 6 && (
        <button
          type="button"
          onClick={() => setAll((v) => !v)}
          className="min-h-11 border-t border-line-soft text-sm text-accent hover:underline"
        >
          {all ? "Show top 6" : `All ${sites.length} sites`}
        </button>
      )}
    </>
  );
}

function Totals({ sites, alerts, loaded }: { sites: SiteSummary[]; alerts: { severity: string; type: string; site_id: number }[]; loaded: boolean }) {
  const count = (level: string) => sites.filter((s) => s.risk?.level === level).length;
  const warning = alerts.filter((a) => a.severity === "warning").length;
  const info = alerts.filter((a) => a.severity === "info").length;
  const danger = alerts.length - warning - info;
  const stopWork = new Set(alerts.filter((a) => a.type === "lightning").map((a) => a.site_id)).size;
  const v = (n: number) => (loaded ? n : "–");
  const tiles = [
    ...[...RISK_LEVELS].reverse().filter((l) => l !== "low").map((l) => ({
      key: l,
      label: RISK_LABELS[l],
      value: v(count(l)),
      detail: l === "extreme" ? "stop non-essential" : l === "high" ? "restricted work" : "precautions",
      color: RISK_COLORS[l],
    })),
    { key: "low", label: "Low", value: v(count("low")), detail: "normal operations", color: RISK_COLORS.low, phoneOnly: true },
    {
      key: "alerts",
      label: "Alerts",
      value: v(alerts.length),
      detail: [danger && `${danger} danger`, `${warning} warn`, `${info} info`].filter(Boolean).join(" · "),
      color: "var(--color-ink)",
    },
    { key: "stop", label: "Stop-work", value: v(stopWork), detail: stopWork ? "lightning ≤ 10 mi" : "none active", color: stopWork ? RISK_TEXT.extreme : "var(--color-ink)" },
  ];
  return (
    <section
      aria-label="Totals"
      className={`grid flex-[3_1_460px] grid-cols-3 overflow-hidden lg:grid-cols-5 ${PANEL} max-lg:bg-card`}
    >
      {tiles.map((t) => (
        <div
          key={t.key}
          className={`flex flex-col gap-1 border-r border-b border-line-soft px-3.5 py-3 lg:border-b-0 ${"phoneOnly" in t ? "lg:hidden" : ""}`}
        >
          <span className="eyebrow">{t.label}</span>
          <span className="font-display text-[30px] leading-none font-extrabold" style={{ color: t.color }}>
            {t.value}
          </span>
          <span className="text-[11px] text-ink-2">{t.detail}</span>
        </div>
      ))}
    </section>
  );
}

function Legend() {
  return (
    <section
      aria-label="Legend"
      className="absolute bottom-2.5 left-2.5 z-[1001] flex flex-col gap-2 rounded-lg bg-panel px-2.5 py-1.5 text-[10px] text-ink-2 lg:top-5 lg:right-5 lg:bottom-auto lg:left-auto lg:rounded-xl lg:border lg:border-line lg:px-3.5 lg:py-3 lg:text-xs"
    >
      <span className="eyebrow hidden lg:block">Legend</span>
      <span className="flex gap-2.5 lg:gap-3">
        {RISK_LEVELS.map((l) => (
          <span key={l} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full lg:h-[9px] lg:w-[9px]" style={{ background: RISK_COLORS[l] }} aria-hidden />
            {RISK_LABELS[l]}
          </span>
        ))}
      </span>
      <span className="hidden gap-3 lg:flex">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full border-[1.5px] border-risk-moderate" aria-hidden />
          NWS alert
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rotate-45 rounded-[1px] bg-ink-2" aria-hidden />
          Crew report
        </span>
        <span className="text-muted">Zoom in for scores</span>
      </span>
    </section>
  );
}
