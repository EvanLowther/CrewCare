"use client";

import { Siren } from "lucide-react";
import { AlertsFeed } from "@/components/AlertsFeed";
import { Card, CardHeader, ErrorBanner, LiveIndicator, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import { useSiteScope } from "@/lib/useSiteScope";
import { ScopeSwitch } from "@/components/ScopeSwitch";

const fetchAlerts = () => api.alerts();

export function AlertsView() {
  const { data, error } = usePolling(fetchAlerts, 10_000);
  const scope = useSiteScope();
  const alerts = (data?.alerts ?? []).filter((a) => scope.includes(a.site_id));
  const sites = new Set(alerts.map((a) => a.site_id)).size;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Alerts"
        subtitle={data ? `${alerts.length} active across ${sites} ${sites === 1 ? "site" : "sites"}` : "Loading alerts…"}
        actions={
          <div className="flex flex-wrap items-center gap-3">
            {scope.available && <ScopeSwitch value={scope.scope} onChange={scope.setScope} />}
            <LiveIndicator label="Live · refreshes every 10 s" />
          </div>
        }
      />
      {error && <ErrorBanner message={error} retrying />}
      <Card className="overflow-hidden">
        <CardHeader title="Active alerts" icon={Siren} subtitle="Most severe first · click a site to open it" />
        <AlertsFeed alerts={alerts} />
      </Card>
    </div>
  );
}
