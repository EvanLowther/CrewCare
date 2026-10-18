"use client";

import { Lock, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useMe } from "@/components/MeProvider";
import { Card, CardHeader, EmptyState, ErrorBanner } from "@/components/ui";
import { api, type AdminUser, type SiteRole, type SiteSummary, type UserRole } from "@/lib/api";
import { relativeTime } from "@/lib/format";

const selectClass =
  "rounded-md border border-line bg-raised px-2 py-1 text-xs text-ink focus:border-accent focus:outline-none";

export function AdminView() {
  const { me, role, refresh: refreshMe } = useMe();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [sites, setSites] = useState<SiteSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [u, s] = await Promise.all([api.adminUsers(), api.sites("rules")]);
      setUsers(u.users);
      setSites([...s.sites].sort((a, b) => a.name.localeCompare(b.name)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load users");
    }
  }, []);

  useEffect(() => {
    // State updates happen when the requests resolve.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (role === "admin") load();
  }, [role, load]);

  if (!me) return <p className="text-sm text-muted">Loading…</p>;
  if (role !== "admin") {
    return (
      <Card>
        <EmptyState icon={Lock} title="Admins only" />
      </Card>
    );
  }

  const changeRole = async (user: AdminUser, next: UserRole) => {
    setError(null);
    try {
      const updated = await api.setRole(user.id, next);
      setUsers((list) => list?.map((u) => (u.id === updated.id ? updated : u)) ?? null);
      setNotice(`${user.name ?? user.email} is now ${next}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't change the role");
    }
  };

  const assign = async (user: AdminUser, siteId: number, siteRole: SiteRole) => {
    setError(null);
    try {
      await api.addMember(siteId, user.id, siteRole);
      const site = sites.find((s) => s.id === siteId);
      setNotice(`Added ${user.name ?? user.email} to ${site?.name ?? "the site"} as ${siteRole}.`);
      setUsers((list) => list?.map((u) => (u.id === user.id ? { ...u, site_count: u.site_count + 1 } : u)) ?? null);
      if (user.id === me.user?.id) refreshMe();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't add them to the site");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {error && <ErrorBanner message={error} />}
      {notice && <p className="rounded-lg border border-line bg-accent-soft px-3 py-2 text-sm text-ink">{notice}</p>}
      <Card className="overflow-hidden">
        <CardHeader
          title="Users"
          icon={ShieldCheck}
          subtitle={users ? `${users.length} signed up · new users start as crew` : "Loading…"}
        />
        <div className="overflow-x-auto border-t border-line">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs text-muted">
              <tr className="border-b border-line">
                <th className="px-5 py-2 font-medium">Person</th>
                <th className="px-3 py-2 font-medium">Role</th>
                <th className="px-3 py-2 font-medium">Sites</th>
                <th className="px-3 py-2 font-medium">Last seen</th>
                <th className="px-5 py-2 font-medium">Add to a site</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(users ?? []).map((u) => (
                <tr key={u.id}>
                  <td className="px-5 py-3">
                    <span className="block text-ink">
                      {u.name ?? u.email}
                      {u.id === me.user?.id && <span className="text-muted"> (you)</span>}
                    </span>
                    {u.name && <span className="block text-xs text-muted">{u.email}</span>}
                  </td>
                  <td className="px-3 py-3">
                    <select
                      value={u.role}
                      aria-label={`Role for ${u.name ?? u.email}`}
                      disabled={u.id === me.user?.id}
                      onChange={(e) => changeRole(u, e.target.value as UserRole)}
                      className={selectClass}
                    >
                      <option value="crew">Crew</option>
                      <option value="manager">Manager</option>
                      <option value="admin">Admin</option>
                    </select>
                  </td>
                  <td className="px-3 py-3 text-ink-2">{u.site_count}</td>
                  <td className="px-3 py-3 text-ink-2">{relativeTime(u.last_seen_at)}</td>
                  <td className="px-5 py-3">
                    <AssignToSite user={u} sites={sites} onAssign={assign} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function AssignToSite({
  user,
  sites,
  onAssign,
}: {
  user: AdminUser;
  sites: SiteSummary[];
  onAssign: (user: AdminUser, siteId: number, role: SiteRole) => void;
}) {
  const [siteId, setSiteId] = useState("");
  const [role, setRole] = useState<SiteRole>("crew");
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select value={siteId} onChange={(e) => setSiteId(e.target.value)} aria-label="Site" className={`${selectClass} max-w-[200px]`}>
        <option value="">Choose a site…</option>
        {sites.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
            {s.is_reference ? "" : " (private)"}
          </option>
        ))}
      </select>
      <select value={role} onChange={(e) => setRole(e.target.value as SiteRole)} aria-label="Role on the site" className={selectClass}>
        <option value="crew">as crew</option>
        {user.role !== "crew" && <option value="manager">as manager</option>}
      </select>
      <button
        type="button"
        disabled={!siteId}
        onClick={() => {
          onAssign(user, Number(siteId), role);
          setSiteId("");
        }}
        className="rounded-md bg-accent-strong px-2.5 py-1 text-xs font-medium text-on-accent hover:bg-accent disabled:opacity-40"
      >
        Add
      </button>
    </div>
  );
}
