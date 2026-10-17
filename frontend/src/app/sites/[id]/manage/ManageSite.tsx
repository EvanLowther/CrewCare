"use client";

import { ArrowLeft, Loader2, Lock, Search, Settings, Trash2, UserPlus, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useMe } from "@/components/MeProvider";
import { SiteForm } from "@/components/SiteForm";
import { Card, CardHeader, EmptyState, ErrorBanner } from "@/components/ui";
import { api, type SiteMember, type SiteRole, type SiteSummary, type User } from "@/lib/api";

export function ManageSite({ id, isNew }: { id: number; isNew: boolean }) {
  const { me, refresh: refreshMe } = useMe();
  const router = useRouter();
  const [site, setSite] = useState<SiteSummary | null>(null);
  const [members, setMembers] = useState<SiteMember[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const viewer = me?.user?.id ?? null;

  const load = useCallback(async () => {
    try {
      const [detail, list] = await Promise.all([api.site(id), api.members(id)]);
      setSite(detail.site);
      setMembers(list.members);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load the site");
    }
  }, [id]);

  useEffect(() => {
    // Load (again) once we know who's signed in; state updates happen when the requests resolve.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (me) load();
  }, [me, viewer, load]);

  if (!me) return <p className="text-sm text-muted">Loading…</p>;
  if (!site) {
    return error ? (
      <Card>
        <EmptyState icon={Lock} title="You can't manage this site" detail={error} />
      </Card>
    ) : (
      <p className="text-sm text-muted">Loading site…</p>
    );
  }
  if (!site.can_manage) {
    return (
      <Card>
        <EmptyState icon={Lock} title="Only this site's managers can manage it" detail="Ask one of its managers or an admin." />
      </Card>
    );
  }

  const onMembers = (list: SiteMember[]) => {
    setMembers(list);
    refreshMe(); // your own membership may have changed
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link href={`/sites/${id}`} className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> {site.name}
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">Manage {site.name}</h1>
        {isNew && (
          <p className="mt-2 rounded-lg border border-line bg-accent-soft px-3 py-2 text-sm text-ink">
            Site created. Add your crew below so they can see it and report hazards. Weather and risk scores appear
            within about 30 minutes.
          </p>
        )}
      </div>
      {error && <ErrorBanner message={error} />}

      <Card>
        <CardHeader title="People on this site" icon={Users} subtitle="Crew see the site and report hazards; managers also run it" />
        <MemberList siteId={id} members={members} viewerId={viewer} onChange={onMembers} onError={setError} />
        <AddPeople siteId={id} members={members} onChange={onMembers} onError={setError} />
      </Card>

      <Card>
        <CardHeader title="Site details" icon={Settings} subtitle={saved ? "Saved" : "Name, location and the description crews see"} />
        <div className="px-5 pb-5">
          <SiteForm
            key={`${site.id}-${site.latitude}-${site.longitude}`}
            initial={{ name: site.name, description: site.description ?? "", latitude: site.latitude, longitude: site.longitude }}
            submitLabel="Save changes"
            onSubmit={async (v) => {
              const updated = await api.updateSite(id, {
                name: v.name,
                description: v.description || null,
                ...(v.latitude !== site.latitude || v.longitude !== site.longitude ? { latitude: v.latitude, longitude: v.longitude } : {}),
              });
              setSite(updated.site);
              setSaved(true);
            }}
          />
        </div>
      </Card>

      {site.can_delete && (
        <Card>
          <CardHeader title="Delete site" icon={Trash2} subtitle="Removes the site, its members, reports and history. This can't be undone." />
          <div className="px-5 pb-5">
            <button
              type="button"
              onClick={async () => {
                if (!window.confirm(`Delete ${site.name}? This removes its history and crew reports for good.`)) return;
                try {
                  await api.deleteSite(id);
                  await refreshMe();
                  router.push("/");
                } catch (e) {
                  setError(e instanceof Error ? e.message : "Couldn't delete the site");
                }
              }}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[rgb(208_59_59/0.5)] px-4 py-2 text-sm text-[#ff9b9b] hover:bg-[rgb(208_59_59/0.12)]"
            >
              <Trash2 className="h-4 w-4" aria-hidden /> Delete {site.name}
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}

function MemberList({
  siteId,
  members,
  viewerId,
  onChange,
  onError,
}: {
  siteId: number;
  members: SiteMember[];
  viewerId: string | null;
  onChange: (list: SiteMember[]) => void;
  onError: (message: string) => void;
}) {
  const act = async (fn: () => Promise<{ members: SiteMember[] }>) => {
    try {
      onChange((await fn()).members);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Couldn't update the site's people");
    }
  };
  if (members.length === 0) return <p className="px-5 pb-3 text-sm text-muted">No one yet.</p>;
  return (
    <ul className="divide-y divide-line border-y border-line">
      {members.map((m) => (
        <li key={m.user_id} className="flex flex-wrap items-center gap-3 px-5 py-3">
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm text-ink">
              {m.name ?? m.email}
              {m.user_id === viewerId && <span className="text-muted"> (you)</span>}
            </span>
            {m.name && <span className="block truncate text-xs text-muted">{m.email}</span>}
          </span>
          <select
            value={m.role}
            aria-label={`Role for ${m.name ?? m.email}`}
            onChange={(e) => act(() => api.addMember(siteId, m.user_id, e.target.value as SiteRole))}
            className="rounded-md border border-line bg-raised px-2 py-1 text-xs text-ink focus:border-accent focus:outline-none"
          >
            <option value="crew">Crew</option>
            <option value="manager">Manager</option>
          </select>
          <button
            type="button"
            onClick={() => act(() => api.removeMember(siteId, m.user_id))}
            className="rounded-md px-2 py-1 text-xs text-ink-2 hover:bg-raised hover:text-ink"
          >
            Remove
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Find people who have signed up, by name or email, and add them as crew (or manager, if they're managers). */
function AddPeople({
  siteId,
  members,
  onChange,
  onError,
}: {
  siteId: number;
  members: SiteMember[];
  onChange: (list: SiteMember[]) => void;
  onError: (message: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<User[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const memberIds = new Set(members.map((m) => m.user_id));

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) return;
    const timer = setTimeout(() => {
      api
        .searchUsers(q)
        .then((r) => setResults(r.users))
        .catch((e: Error) => onError(e.message));
    }, 250);
    return () => clearTimeout(timer);
  }, [query, onError]);

  const add = async (user: User, role: SiteRole) => {
    setBusy(user.id);
    try {
      onChange((await api.addMember(siteId, user.id, role)).members);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Couldn't add them");
    } finally {
      setBusy(null);
    }
  };

  const shown = query.trim().length >= 2 ? results : null;
  return (
    <div className="px-5 py-4">
      <label className="flex items-center gap-2 rounded-lg border border-line bg-raised px-3 py-2 text-sm focus-within:border-accent">
        <Search className="h-4 w-4 shrink-0 text-muted" aria-hidden />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Add people: search by name or email"
          aria-label="Search people to add"
          className="w-full bg-transparent text-ink placeholder:text-muted focus:outline-none"
        />
      </label>
      <p className="mt-1.5 text-xs text-muted">People need to sign in once before you can add them.</p>
      {shown && (
        <ul className="mt-2 divide-y divide-line rounded-lg border border-line">
          {shown.length === 0 && <li className="px-3 py-2 text-xs text-muted">No one matches. Have them sign in first.</li>}
          {shown.map((u) => (
            <li key={u.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-ink">{u.name ?? u.email}</span>
                <span className="block truncate text-xs text-muted">
                  {u.email} · {u.role}
                </span>
              </span>
              {memberIds.has(u.id) ? (
                <span className="text-xs text-muted">On this site</span>
              ) : busy === u.id ? (
                <Loader2 className="h-4 w-4 animate-spin text-muted" aria-hidden />
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => add(u, "crew")}
                    className="inline-flex items-center gap-1 rounded-md bg-accent-strong px-2.5 py-1 text-xs font-medium text-white hover:bg-accent"
                  >
                    <UserPlus className="h-3.5 w-3.5" aria-hidden /> Add as crew
                  </button>
                  {u.role !== "crew" && (
                    <button
                      type="button"
                      onClick={() => add(u, "manager")}
                      className="rounded-md border border-line px-2.5 py-1 text-xs text-ink-2 hover:text-ink"
                    >
                      Add as manager
                    </button>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
