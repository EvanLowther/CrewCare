"use client";

import { BellOff } from "lucide-react";
import Link from "next/link";
import type { Alert } from "@/lib/api";
import { alertEndsAt, alertLabel, inForce, SEVERITY_RANK } from "@/lib/alerts";
import { alertKind, HAZARD_KINDS, kindChipStyle } from "@/lib/hazardKinds";
import { relativeTime } from "@/lib/format";
import { useNow } from "@/lib/useNow";
import { EmptyState, SeverityBadge } from "./ui";

/** Table of alerts, most severe first. Rows link to the site page. */
export function AlertsFeed({ alerts, limit }: { alerts: Alert[]; limit?: number }) {
  const now = useNow(15_000);
  const sorted = alerts.filter((a) => inForce(a, now)).sort(
    (a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || b.started_at.localeCompare(a.started_at),
  );
  const shown = limit ? sorted.slice(0, limit) : sorted;

  if (shown.length === 0) {
    return <EmptyState icon={BellOff} title="No active alerts" detail="NWS warnings and stop-work alerts show up here within 5 minutes." />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-y border-line text-xs text-muted">
            <th className="px-5 py-2.5 font-medium">Site</th>
            <th className="px-3 py-2.5 font-medium">Hazard</th>
            <th className="px-3 py-2.5 font-medium">Severity</th>
            <th className="px-3 py-2.5 font-medium">Details</th>
            <th className="px-3 py-2.5 font-medium">Started</th>
            <th className="px-5 py-2.5 text-right font-medium">Ends</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {shown.map((alert) => {
            const kind = alertKind(alert);
            const Icon = HAZARD_KINDS[kind].icon;
            const ends = alertEndsAt(alert);
            return (
              <tr key={alert.id} className="transition-colors hover:bg-raised">
                <td className="px-5 py-3">
                  <Link href={`/sites/${alert.site_id}`} className="whitespace-nowrap font-medium text-ink hover:text-accent">
                    {alert.site_name}
                  </Link>
                </td>
                <td className="px-3 py-3">
                  <span className="inline-flex items-center gap-2 whitespace-nowrap text-ink-2">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md" style={kindChipStyle(kind)}>
                      <Icon className="h-3.5 w-3.5" aria-hidden />
                    </span>
                    {alertLabel(alert)}
                  </span>
                </td>
                <td className="px-3 py-3">
                  <SeverityBadge severity={alert.severity} />
                </td>
                <td className="max-w-[340px] px-3 py-3">
                  <span className="line-clamp-1 text-ink-2" title={alert.title}>
                    {alert.title}
                  </span>
                </td>
                <td className="tabular whitespace-nowrap px-3 py-3 text-ink-2">{relativeTime(alert.started_at)}</td>
                <td className="tabular whitespace-nowrap px-5 py-3 text-right text-ink-2">
                  {ends ? relativeTime(ends) : "–"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
