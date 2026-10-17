"use client";

import { Bell, Map as MapIcon, OctagonAlert, Siren, TrendingUp } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useState } from "react";
import { api, type Scorer } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import { AlertsFeed } from "./AlertsFeed";
import { MODEL_LABELS, ModelSwitch } from "./ModelSwitch";
import { SiteList } from "./SiteList";
import { Card, CardHeader, ErrorBanner, LiveIndicator, PageHeader, RiskLegend, StatTile } from "./ui";

// Leaflet needs `window`, so the map only renders in the browser.
const SiteMap = dynamic(() => import("./SiteMap"), {
  ssr: false,
  loading: () => <div className="flex h-full items-center justify-center text-sm text-muted">Loading map…</div>,
});

const POLL_MS = 10_000;
const fetchAlerts = () => api.alerts();
const fetchReports = () => api.reports();

export function Dashboard() {
  const [model, setModel] = useState<Scorer>("ml");
  const fetchSites = useCallback(() => api.sites(model), [model]);
  const sitesPoll = usePolling(fetchSites, POLL_MS);
  const alertsPoll = usePolling(fetchAlerts, POLL_MS);
  const reportsPoll = usePolling(fetchReports, POLL_MS);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const sites = sitesPoll.data?.sites ?? [];
  const alerts = alertsPoll.data?.alerts ?? [];
  const anyScored = sites.some((s) => s.risk !== null);
  const danger = alerts.filter((a) => a.severity === "danger").length;
  const warning = alerts.filter((a) => a.severity === "warning").length;
  const stopWork = [...new Map(alerts.filter((a) => a.type === "lightning").map((a) => [a.site_id, a])).values()];
  const error = sitesPoll.error ?? alertsPoll.error;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Site risk dashboard"
        subtitle={
          sitesPoll.data
            ? `${sites.length} sites · updated ${new Date(sitesPoll.data.updated_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`
            : "Loading sites…"
        }
        actions={<LiveIndicator label="Live · refreshes every 10 s" />}
      />

      {error && <ErrorBanner message={error} />}

      <div className="grid gap-4 sm:grid-cols-2">
        <StatTile
          label="Active alerts"
          icon={Bell}
          value={alertsPoll.data ? alerts.length : "–"}
          detail={alertsPoll.data ? `${danger} danger · ${warning} warning · ${alerts.length - danger - warning} info` : " "}
        />
        <StatTile
          label="Stop-work sites"
          icon={OctagonAlert}
          tone={stopWork.length ? "danger" : "default"}
          value={alertsPoll.data ? stopWork.length : "–"}
          detail={
            stopWork.length ? (
              <span className="flex flex-wrap gap-x-2">
                {stopWork.map((a) => (
                  <Link key={a.site_id} href={`/sites/${a.site_id}`} className="text-[#ff9b9b] hover:underline">
                    {a.site_name}
                  </Link>
                ))}
              </span>
            ) : (
              "No lightning within 10 miles of any site"
            )
          }
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="flex flex-col overflow-hidden">
          <CardHeader
            title="Site map"
            icon={MapIcon}
            subtitle={`${MODEL_LABELS[model]} scores (0-10); pulsing pins have an active alert`}
            actions={<RiskLegend />}
          />
          <div className="relative h-[55vh] min-h-[360px] border-t border-line xl:h-[calc(100vh-24rem)] xl:min-h-[520px]">
            <SiteMap
              sites={sites}
              selectedId={selectedId}
              onSelect={setSelectedId}
              model={model}
              reports={reportsPoll.data?.reports ?? []}
            />
            {/* Above Leaflet's panes and controls (z-index up to 1000). */}
            <div className="absolute right-3 top-3 z-1001">
              <ModelSwitch value={model} onChange={setModel} />
            </div>
          </div>
        </Card>
        <Card className="flex flex-col overflow-hidden">
          <CardHeader
            title={anyScored || !sitesPoll.data ? "Highest risk first" : "Largest plants first"}
            icon={TrendingUp}
            subtitle={anyScored || !sitesPoll.data ? `${MODEL_LABELS[model]} · updated every 5 minutes` : "No risk scores yet"}
          />
          <div className="max-h-[420px] overflow-y-auto border-t border-line xl:h-[calc(100vh-24rem)] xl:max-h-none xl:min-h-[520px]">
            <SiteList sites={sites} selectedId={selectedId} onSelect={setSelectedId} />
          </div>
        </Card>
      </div>

      <Card className="overflow-hidden">
        <CardHeader
          title="Live alerts"
          icon={Siren}
          subtitle="NWS warnings and stop-work alerts across all sites, most severe first"
          actions={
            <Link href="/alerts" className="text-xs font-medium text-accent hover:underline">
              View all
            </Link>
          }
        />
        <AlertsFeed alerts={alerts} limit={8} />
      </Card>
    </div>
  );
}
