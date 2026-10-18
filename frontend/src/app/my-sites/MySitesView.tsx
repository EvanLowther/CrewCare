"use client";

import { ArrowLeft, Building2, Check, ChevronRight, ClipboardList, ExternalLink, LogIn, Plus, Search, Settings } from "lucide-react";
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { useMe } from "@/components/MeProvider";
import { Card, EmptyState, ErrorBanner, PageHeader, ScoreChip } from "@/components/ui";
import { api, type HazardReport, type SiteSummary } from "@/lib/api";
import { DEV_AUTH, signInHref } from "@/lib/auth";
import { relativeTime } from "@/lib/format";
import { HAZARD_ICONS, HAZARD_LABELS, REPORT_SEVERITY_COLORS } from "@/lib/reports";
import { usePolling } from "@/lib/usePolling";
import { useNow } from "@/lib/useNow";

const fetchSites = () => api.sites();
const fetchActiveReports = () => api.reports();

const ROLE_LABELS = { manager: "Manager", crew: "Crew" } as const;

/** Your sites on the left (or above, on a phone); the chosen site's crew reports on the right. */
export function MySitesView({ siteId }: { siteId: number | null }) {
  const { me, role, signedIn } = useMe();
  const sitesPoll = usePolling(fetchSites, 60_000);
  const reportsPoll = usePolling(fetchActiveReports, 30_000);
  const [scope, setScope] = useState<"mine" | "all">("mine");
  const [query, setQuery] = useState("");

  const myRoles = useMemo(() => new Map((me?.sites ?? []).map((s) => [s.site_id, s.role])), [me]);
  const summaries = useMemo(() => new Map((sitesPoll.data?.sites ?? []).map((s) => [s.id, s])), [sitesPoll.data]);
  const activeCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const r of reportsPoll.data?.reports ?? []) if (r.site_id !== null) counts.set(r.site_id, (counts.get(r.site_id) ?? 0) + 1);
    return counts;
  }, [reportsPoll.data]);

  if (!me) return <p className="text-sm text-muted">Loading your sites…</p>;
  if (!signedIn) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="My sites" />
        <Card>
          <EmptyState icon={LogIn} title="Sign in to see your sites" detail="Your sites and their crew reports show up here once you're signed in." />
          {!DEV_AUTH && (
            <div className="flex justify-center pb-6">
              <a href={signInHref("/my-sites")} className="rounded-lg bg-accent-strong px-4 py-2 text-sm font-semibold text-on-accent">
                Sign in
              </a>
            </div>
          )}
        </Card>
      </div>
    );
  }

  const isAdmin = role === "admin";
  const showAll = isAdmin && scope === "all";
  // Members' sites by name (from /api/me, so they show before the scores load); admins can switch to every site.
  const base: { id: number; name: string }[] = showAll
    ? [...summaries.values()].map((s) => ({ id: s.id, name: s.name }))
    : (me.sites ?? []).map((s) => ({ id: s.site_id, name: s.site_name }));
  const q = query.trim().toLowerCase();
  const list = base
    .filter((s) => !q || `${s.name} ${summaries.get(s.id)?.county ?? ""}`.toLowerCase().includes(q))
    .sort((a, b) => a.name.localeCompare(b.name));
  const selected = siteId !== null ? summaries.get(siteId) : undefined;

  return (
    <div className="flex flex-col gap-6">
      <div className={siteId !== null ? "hidden lg:block" : ""}>
        <PageHeader
          title="My sites"
          subtitle="Pick a site to see its crew reports. Managers can manage the site and resolve reports here."
          actions={
            <Link
              href="/report"
              className="inline-flex min-h-9 items-center gap-2 rounded-lg bg-accent-strong px-4 text-sm font-semibold text-on-accent"
            >
              <Plus className="h-4 w-4" aria-hidden /> Report hazard
            </Link>
          }
        />
      </div>
      {sitesPoll.error && <ErrorBanner message={sitesPoll.error} retrying />}

      <div className="grid items-start gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        {/* The list. On a phone it hides while a site is open; the back button brings it back. */}
        <Card className={`overflow-hidden ${siteId !== null ? "hidden lg:block" : ""}`}>
          <div className="flex flex-col gap-3 border-b border-line p-4">
            {isAdmin && (
              <div role="group" aria-label="Which sites" className="flex rounded-[10px] border border-line bg-[#0c1018] p-1">
                {(["mine", "all"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    aria-pressed={scope === s}
                    onClick={() => setScope(s)}
                    className={`min-h-8 flex-1 rounded-[7px] text-[13px] transition-colors ${
                      scope === s ? "bg-accent-strong font-semibold text-on-accent" : "text-ink-2 hover:text-ink"
                    }`}
                  >
                    {s === "mine" ? "My sites" : "All sites"}
                  </button>
                ))}
              </div>
            )}
            <label className="flex min-h-10 items-center gap-2 rounded-lg border border-line bg-raised px-3 text-sm focus-within:border-accent">
              <Search className="h-4 w-4 text-muted" aria-hidden />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Find a site"
                aria-label="Find a site"
                className="w-full min-w-0 bg-transparent text-ink placeholder:text-muted focus:outline-none"
              />
            </label>
          </div>
          {list.length === 0 ? (
            <EmptyState
              icon={Building2}
              title={q ? "No matching sites" : "You're not on any sites yet"}
              detail={
                q
                  ? undefined
                  : role === "manager"
                    ? "Create a site and add your crew, or ask a manager to add you to theirs."
                    : "A manager adds you to their site; it shows up here then."
              }
            />
          ) : (
            <ul className="max-h-[70vh] divide-y divide-line overflow-y-auto">
              {list.map((s) => {
                const summary = summaries.get(s.id);
                const myRole = myRoles.get(s.id);
                const count = activeCounts.get(s.id) ?? 0;
                const active = s.id === siteId;
                return (
                  <li key={s.id}>
                    <Link
                      href={`/my-sites?site=${s.id}`}
                      scroll={false}
                      aria-current={active ? "page" : undefined}
                      className={`flex items-center gap-3 px-4 py-3 transition-colors ${active ? "bg-accent-soft" : "hover:bg-raised"}`}
                    >
                      <ScoreChip score={summary?.risk?.score ?? null} level={summary?.risk?.level ?? null} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-ink">{s.name}</span>
                        <span className="block truncate text-xs text-muted">
                          {[myRole ? ROLE_LABELS[myRole] : null, summary?.county ? `${summary.county} County` : null]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </span>
                      {count > 0 && (
                        <span className="rounded-full bg-[rgb(245_184_61/0.16)] px-2 py-0.5 font-mono text-[11px] text-risk-moderate" title={`${count} active reports`}>
                          {count}
                        </span>
                      )}
                      <ChevronRight className="h-4 w-4 shrink-0 text-muted" aria-hidden />
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <div className={siteId === null ? "hidden lg:block" : ""}>
          {siteId === null ? (
            <Card>
              <EmptyState icon={ClipboardList} title="Pick a site" detail="Its crew reports show here: active ones first, then past ones." />
            </Card>
          ) : !sitesPoll.data ? (
            <p className="text-sm text-muted">Loading site…</p>
          ) : !selected ? (
            <Card>
              <BackToList />
              <EmptyState icon={Building2} title="Site not found" detail="It may have been deleted, or you're not on it." />
            </Card>
          ) : (
            <SiteReports key={selected.id} site={selected} myRole={myRoles.get(selected.id) ?? null} isAdmin={isAdmin} />
          )}
        </div>
      </div>
    </div>
  );
}

function BackToList() {
  return (
    <Link href="/my-sites" scroll={false} className="inline-flex min-h-10 items-center gap-1.5 px-5 pt-4 text-sm text-accent hover:underline">
      <ArrowLeft className="h-4 w-4" aria-hidden /> All my sites
    </Link>
  );
}

function SiteReports({ site, myRole, isAdmin }: { site: SiteSummary; myRole: "manager" | "crew" | null; isAdmin: boolean }) {
  const fetchReports = useCallback(() => api.reports(site.id, true), [site.id]);
  const { data, error } = usePolling(fetchReports, 20_000);
  const now = useNow(60_000);
  const [resolved, setResolved] = useState<Map<string, string>>(new Map());
  const [resolveError, setResolveError] = useState<string | null>(null);
  const canManage = site.can_manage || isAdmin;
  const canReport = myRole !== null || isAdmin;

  const reports = (data?.reports ?? []).map((r) =>
    resolved.has(r.id) ? { ...r, status: "resolved" as const, resolved_at: resolved.get(r.id) ?? null } : r,
  );
  const isActive = (r: HazardReport) => r.status === "active" && (!r.expires_at || new Date(r.expires_at).getTime() > now);
  const active = reports.filter(isActive);
  const past = reports.filter((r) => !isActive(r));

  async function resolve(r: HazardReport) {
    setResolveError(null);
    try {
      const updated = await api.resolveReport(r.id);
      setResolved((prev) => new Map(prev).set(r.id, updated.resolved_at ?? new Date().toISOString()));
    } catch (e) {
      setResolveError(e instanceof Error ? e.message : "Couldn't resolve the report");
    }
  }

  return (
    <Card className="overflow-hidden">
      <BackToList />
      <header className="flex flex-wrap items-start justify-between gap-4 px-5 pt-3 pb-4">
        <div className="flex min-w-0 items-center gap-3">
          <ScoreChip score={site.risk?.score ?? null} level={site.risk?.level ?? null} size="lg" />
          <div className="min-w-0">
            <h2 className="truncate font-display text-3xl leading-tight font-extrabold text-ink">{site.name}</h2>
            <p className="text-xs text-muted">
              {[myRole ? ROLE_LABELS[myRole] : isAdmin ? "Admin" : null, site.county ? `${site.county} County` : null]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href={`/sites/${site.id}`} className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line px-3 text-sm text-ink hover:border-accent">
            <ExternalLink className="h-4 w-4" aria-hidden /> Site page
          </Link>
          {canManage && (
            <Link
              href={`/sites/${site.id}/manage`}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line px-3 text-sm text-ink hover:border-accent"
            >
              <Settings className="h-4 w-4" aria-hidden /> Manage site
            </Link>
          )}
          {canReport && (
            <Link
              href={`/report?site=${site.id}`}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-accent-strong px-3 text-sm font-semibold text-on-accent"
            >
              <Plus className="h-4 w-4" aria-hidden /> Report hazard
            </Link>
          )}
        </div>
      </header>

      {error && (
        <div className="px-5 pb-3">
          <ErrorBanner message={error} retrying />
        </div>
      )}
      {resolveError && <p className="px-5 pb-3 text-sm text-[#ff9b9b]">{resolveError}</p>}

      {!data ? (
        <p className="px-5 pb-5 text-sm text-muted">Loading reports…</p>
      ) : (
        <>
          <ReportSection title="Active reports" empty="No active reports. Crews' reports show here as soon as they're filed.">
            {active.map((r) => (
              <ReportRow key={r.id} r={r} now={now} onResolve={canManage ? () => resolve(r) : undefined} />
            ))}
          </ReportSection>
          <ReportSection title="Past reports" empty="No resolved or expired reports yet." muted>
            {past.map((r) => (
              <ReportRow key={r.id} r={r} now={now} past />
            ))}
          </ReportSection>
        </>
      )}
    </Card>
  );
}

function ReportSection({ title, empty, muted = false, children }: { title: string; empty: string; muted?: boolean; children: React.ReactNode[] }) {
  return (
    <section aria-label={title} className="border-t border-line">
      <h3 className={`px-5 pt-4 pb-2 text-xs font-semibold ${muted ? "text-muted" : "text-ink-2"}`}>
        {title} <span className="font-normal text-muted">· {children.length}</span>
      </h3>
      {children.length === 0 ? <p className="px-5 pb-4 text-sm text-muted">{empty}</p> : <ul className="divide-y divide-line">{children}</ul>}
    </section>
  );
}

function ReportRow({ r, now, past = false, onResolve }: { r: HazardReport; now: number; past?: boolean; onResolve?: () => void }) {
  const Icon = HAZARD_ICONS[r.hazard_type];
  const color = REPORT_SEVERITY_COLORS[r.severity];
  const pastLabel =
    r.status === "resolved"
      ? `Resolved ${r.resolved_at ? relativeTime(r.resolved_at, now) : ""}`.trim()
      : r.expires_at
        ? `Expired ${relativeTime(r.expires_at, now)}`
        : "Closed";
  return (
    <li className={`flex gap-3 px-5 py-3 ${past ? "opacity-75" : ""}`}>
      <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg" style={{ background: `${color}26`, color }}>
        <Icon className="h-4 w-4" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-medium text-ink">{HAZARD_LABELS[r.hazard_type]}</span>
          <span className="rounded-full px-2 py-px text-[11px] capitalize" style={{ background: `${color}26`, color }}>
            {r.severity}
          </span>
          {past && <span className="text-xs text-muted">{pastLabel}</span>}
        </p>
        {r.description && <p className="mt-0.5 text-sm text-ink-2">{r.description}</p>}
        <p className="mt-0.5 text-xs text-muted">
          {r.reporter_name ? `${r.reporter_name} · ` : ""}
          {relativeTime(r.created_at, now)}
          {!past && r.expires_at ? ` · clears ${relativeTime(r.expires_at, now)}` : ""}
        </p>
      </div>
      {r.photo_url && (
        <a href={api.photoUrl(r.photo_url)} target="_blank" rel="noreferrer" className="shrink-0" aria-label="Open photo">
          {/* eslint-disable-next-line @next/next/no-img-element -- signed API photo URL */}
          <img src={api.photoUrl(r.photo_url)} alt="" className="h-14 w-14 rounded-lg object-cover" />
        </a>
      )}
      {onResolve && (
        <button
          type="button"
          onClick={onResolve}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 self-center rounded-lg border border-line px-3 text-xs text-ink hover:border-accent"
        >
          <Check className="h-3.5 w-3.5" aria-hidden /> Resolve
        </button>
      )}
    </li>
  );
}
