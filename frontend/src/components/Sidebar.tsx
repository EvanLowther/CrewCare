"use client";

import {
  Bell,
  Camera,
  FileText,
  LayoutDashboard,
  LogIn,
  LogOut,
  Menu,
  MapPinPlus,
  Search,
  ShieldCheck,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Suspense, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api, type SiteSummary } from "@/lib/api";
import { DEV_AUTH, DEV_USERS, devUser, setDevUser, SIGN_OUT_HREF, signInHref } from "@/lib/auth";
import { usePolling } from "@/lib/usePolling";
import { useMe } from "./MeProvider";
import { ScoreChip } from "./ui";

const fetchAlerts = () => api.alerts();

type NavItem = { href: string; label: string; icon: LucideIcon; badge?: "alerts"; show?: "manager" | "admin" };

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/alerts", label: "Alerts", icon: Bell, badge: "alerts" },
  { href: "/report", label: "Crew reports", icon: Camera },
  { href: "/briefings", label: "Briefings", icon: FileText },
  { href: "/sites/new", label: "New site", icon: MapPinPlus, show: "manager" },
  { href: "/admin", label: "Admin", icon: ShieldCheck, show: "admin" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/" || (pathname.startsWith("/sites") && pathname !== "/sites/new");
  return pathname.startsWith(href);
}

const ROLE_LABELS = { admin: "Admin", manager: "Manager", crew: "Crew" } as const;

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-cyan shadow-[0_4px_16px_rgb(110_123_255/0.45)]">
        <Zap className="h-4 w-4 text-white" aria-hidden />
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-ink">PlanIT Control</span>
    </Link>
  );
}

/** Type a site name or county; Enter or click jumps to its page. */
function SiteSearch({ onNavigate }: { onNavigate?: () => void }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [sites, setSites] = useState<SiteSummary[] | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const loadSites = () => {
    if (sites === null) api.sites().then((r) => setSites(r.sites)).catch(() => setSites([]));
  };

  const q = query.trim().toLowerCase();
  const results = q
    ? (sites ?? []).filter((s) => `${s.name} ${s.county ?? ""} ${s.utility ?? ""}`.toLowerCase().includes(q)).slice(0, 6)
    : [];

  const go = (site: SiteSummary) => {
    setQuery("");
    setOpen(false);
    onNavigate?.();
    router.push(`/sites/${site.id}`);
  };

  return (
    <div ref={boxRef} className="relative">
      <label className="flex items-center gap-2 rounded-lg border border-line bg-card px-3 py-2 text-sm focus-within:border-accent">
        <Search className="h-4 w-4 shrink-0 text-muted" aria-hidden />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
            setOpen(true);
          }}
          onFocus={() => {
            loadSites();
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, results.length - 1));
            else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
            else if (e.key === "Enter" && results[active]) go(results[active]);
            else if (e.key === "Escape") setOpen(false);
          }}
          placeholder="Search sites…"
          aria-label="Search sites"
          className="w-full bg-transparent text-ink placeholder:text-muted focus:outline-none"
        />
      </label>
      {open && q && (
        <ul className="absolute inset-x-0 top-full z-[1100] mt-1 overflow-hidden rounded-lg border border-line bg-raised shadow-xl">
          {results.length === 0 ? (
            <li className="px-3 py-2 text-xs text-muted">{sites === null ? "Loading…" : "No matching sites"}</li>
          ) : (
            results.map((s, i) => (
              <li key={s.id}>
                <button
                  type="button"
                  onMouseEnter={() => setActive(i)}
                  onClick={() => go(s)}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left ${i === active ? "bg-accent-soft" : ""}`}
                >
                  <ScoreChip score={s.risk?.score ?? null} level={s.risk?.level ?? null} />
                  <span className="min-w-0">
                    <span className="block truncate text-sm text-ink">{s.name}</span>
                    <span className="block truncate text-xs text-muted">{s.county} County</span>
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

// usePathname() is runtime data in Next 16, so it must render inside <Suspense>.
function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <Suspense fallback={<NavList pathname={null} onNavigate={onNavigate} />}>
      <ActiveNavLinks onNavigate={onNavigate} />
    </Suspense>
  );
}

function ActiveNavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return <NavList pathname={usePathname()} onNavigate={onNavigate} />;
}

function NavList({ pathname, onNavigate }: { pathname: string | null; onNavigate?: () => void }) {
  const { data } = usePolling(fetchAlerts, 30_000);
  const { role } = useMe();
  const alertCount = data?.alerts.length ?? 0;
  const items = NAV.filter(
    (n) => !n.show || role === "admin" || (n.show === "manager" && role === "manager"),
  );

  return (
    <nav className="flex flex-col gap-1" aria-label="Main">
      {items.map(({ href, label, icon: Icon, badge }) => {
        const active = pathname !== null && isActive(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
              active
                ? "bg-accent-soft text-ink shadow-[inset_3px_0_0_var(--color-accent)]"
                : "text-ink-2 hover:bg-raised hover:text-ink"
            }`}
          >
            <Icon className={`h-4 w-4 ${active ? "text-accent" : ""}`} aria-hidden />
            <span className="flex-1">{label}</span>
            {badge === "alerts" && alertCount > 0 && (
              <span className="rounded-full bg-[rgb(208_59_59/0.2)] px-2 py-0.5 text-xs font-medium text-[#ff8a8a]">
                {alertCount}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

/** Sign in / out, and who you are. On laptops (NEXT_PUBLIC_AUTH_DEV=1) a "Sign in as" menu of fake users. */
const noSubscribe = () => () => {};

function Account() {
  const { me } = useMe();
  const user = me?.user;
  // localStorage only exists in the browser; the server renders "signed out" and the browser fills it in.
  const currentDevUser = useSyncExternalStore(noSubscribe, devUser, () => null);

  if (DEV_AUTH) {
    return (
      <label className="block rounded-lg border border-dashed border-line bg-card px-3 py-2.5 text-xs">
        <span className="mb-1 block font-medium text-muted">Sign in as (dev)</span>
        <select
          value={currentDevUser ?? ""}
          onChange={(e) => setDevUser(e.target.value || null)}
          className="w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink focus:border-accent focus:outline-none"
        >
          <option value="">Signed out</option>
          {DEV_USERS.map((u) => (
            <option key={u.key} value={u.key}>
              {u.label} ({u.role})
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (!me) return <div className="h-[52px] rounded-lg border border-line bg-card" aria-hidden />;
  if (!user) {
    return (
      // A full page load (not <Link>): Auth0's login is a redirect handled by the server.
      <a
        href="/auth/login"
        onClick={(e) => {
          // Come back to the page they were on.
          e.currentTarget.href = signInHref(window.location.pathname + window.location.search);
        }}
        className="flex items-center justify-center gap-2 rounded-lg border border-line bg-card px-4 py-2.5 text-sm font-medium text-ink hover:border-accent"
      >
        <LogIn className="h-4 w-4 text-accent" aria-hidden />
        Sign in
      </a>
    );
  }
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-line bg-card px-3 py-2.5">
      {user.picture ? (
        // eslint-disable-next-line @next/next/no-img-element -- Auth0/Google avatar
        <img src={user.picture} alt="" className="h-8 w-8 rounded-full" referrerPolicy="no-referrer" />
      ) : (
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-sm font-medium text-accent">
          {(user.name ?? user.email ?? "?").slice(0, 1).toUpperCase()}
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-ink">{user.name ?? user.email}</span>
        <span className="text-xs text-muted">{ROLE_LABELS[user.role]}</span>
      </span>
      <a href={SIGN_OUT_HREF} aria-label="Sign out" title="Sign out" className="p-1.5 text-ink-2 hover:text-ink">
        <LogOut className="h-4 w-4" aria-hidden />
      </a>
    </div>
  );
}

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col gap-6 px-4 py-5">
      <div className="hidden lg:block">
        <Logo />
      </div>
      <SiteSearch onNavigate={onNavigate} />
      <NavLinks onNavigate={onNavigate} />
      <div className="mt-auto space-y-3">
        <Account />
        <Link
          href="/report"
          onClick={onNavigate}
          className="flex items-center justify-center gap-2 rounded-lg bg-accent-strong px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent"
        >
          <Camera className="h-4 w-4" aria-hidden />
          Report hazard
        </Link>
      </div>
    </div>
  );
}

export function Sidebar() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Phones and tablets: top bar + slide-in drawer */}
      <div className="sticky top-0 z-[1000] flex items-center justify-between border-b border-line bg-sidebar/95 px-4 py-3 backdrop-blur lg:hidden">
        <Logo />
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          className="rounded-lg border border-line p-2 text-ink-2 hover:text-ink"
        >
          <Menu className="h-5 w-5" aria-hidden />
        </button>
      </div>
      {open && (
        <div className="fixed inset-0 z-[1200] lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <button type="button" aria-label="Close menu" className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-line bg-sidebar">
            <div className="flex items-center justify-between px-4 pt-4">
              <Logo />
              <button type="button" onClick={() => setOpen(false)} aria-label="Close menu" className="p-2 text-ink-2">
                <X className="h-5 w-5" aria-hidden />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <SidebarBody onNavigate={() => setOpen(false)} />
            </div>
          </aside>
        </div>
      )}

      {/* Desktop: fixed sidebar */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-line bg-sidebar lg:block">
        <SidebarBody />
      </aside>
    </>
  );
}
