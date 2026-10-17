"use client";

import { Siren } from "lucide-react";
import { AlertsFeed } from "@/components/AlertsFeed";
import { Card, CardHeader, ErrorBanner, LiveIndicator, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

const fetchAlerts = () => api.alerts();

export function AlertsView() {
  const { data, error } = usePolling(fetchAlerts, 10_000);
  const alerts = data?.alerts ?? [];
  const sites = new Set(alerts.map((a) => a.site_id)).size;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Alerts"
        subtitle={data ? `${alerts.length} active across ${sites} ${sites === 1 ? "site" : "sites"}` : "Loading alerts…"}
        actions={<LiveIndicator label="Live · refreshes every 10 s" />}
      />
      {error && <ErrorBanner message={error} />}
      <Card className="overflow-hidden">
        <CardHeader title="Active alerts" icon={Siren} subtitle="Most severe first · click a site to open it" />
        <AlertsFeed alerts={alerts} />
      </Card>
    </div>
  );
}
