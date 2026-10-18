"use client";

import { LogIn, LogOut, Menu, Plus, Search, TriangleAlert, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Suspense, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { api, type SiteSummary } from "@/lib/api";
import { DEV_AUTH, DEV_USERS, devUser, setDevUser, SIGN_OUT_HREF, signInHref } from "@/lib/auth";
import { usePolling } from "@/lib/usePolling";
import { useMe } from "./MeProvider";
import { Inbox } from "./Notifications";
import { ScoreChip } from "./ui";

const fetchAlerts = () => api.alerts();

type NavItem = { href: string; label: string; badge?: "alerts"; show?: "admin" };

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard" },
  { href: "/alerts", label: "Alerts", badge: "alerts" },
  { href: "/briefings", label: "Briefings" },
  { href: "/my-sites", label: "Sites" },
  { href: "/admin", label: "Admin", show: "admin" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/" || (pathname.startsWith("/sites") && pathname !== "/sites/new");
  // The new-site form is reached from the Sites page, so it stays under that tab.
  if (href === "/my-sites") return pathname.startsWith("/my-sites") || pathname === "/sites/new";
  return pathname.startsWith(href);
}

const ROLE_LABELS = { admin: "Admin", manager: "Manager", crew: "Crew" } as const;

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5 text-ink">
      <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden>
        <rect x="1" y="1" width="24" height="24" rx="5" fill="none" stroke="var(--color-accent)" strokeWidth="1.5" />
        <path d="M8 19 V13 M13 19 V7 M18 19 V10" stroke="var(--color-accent)" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span className="font-display text-[20px] font-extrabold tracking-[0.06em] whitespace-nowrap sm:text-[22px]">CREWCARE</span>
    </Link>
  );
}

function useAlertCount() {
  const { data } = usePolling(fetchAlerts, 30_000);
  return data?.alerts.length ?? 0;
}

function AlertBadge({ count }: { count: number }) {
  if (count === 0) return null;
  return (
    <span className="rounded-full bg-[rgb(245_184_61/0.16)] px-1.5 py-px font-mono text-[11px] text-risk-moderate">{count}</span>
  );
}

/** Type a site name or county; Enter or click jumps to its page. */
export function SiteSearch({ onNavigate, className = "" }: { onNavigate?: () => void; className?: string }) {
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
    <div ref={boxRef} className={`relative ${className}`}>
      <label className="flex min-h-10 items-center gap-2 rounded-full bg-raised px-3 text-sm focus-within:ring-1 focus-within:ring-accent">
        <Search className="h-4 w-4 shrink-0 text-muted" aria-hidden />
        <input
          type="search"
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
          placeholder="Site or county"
          aria-label="Search sites"
          className="w-full min-w-0 bg-transparent text-ink placeholder:text-muted focus:outline-none"
        />
      </label>
      {open && q && (
        <ul className="absolute inset-x-0 top-full z-[1100] mt-1 min-w-64 overflow-hidden rounded-xl border border-line bg-raised shadow-xl">
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
function NavLinks({ vertical = false, onNavigate }: { vertical?: boolean; onNavigate?: () => void }) {
  return (
    <Suspense fallback={<NavList pathname={null} vertical={vertical} onNavigate={onNavigate} />}>
      <ActiveNavLinks vertical={vertical} onNavigate={onNavigate} />
    </Suspense>
  );
}

function ActiveNavLinks({ vertical, onNavigate }: { vertical: boolean; onNavigate?: () => void }) {
  return <NavList pathname={usePathname()} vertical={vertical} onNavigate={onNavigate} />;
}

function NavList({ pathname, vertical, onNavigate }: { pathname: string | null; vertical: boolean; onNavigate?: () => void }) {
  const alertCount = useAlertCount();
  const { role } = useMe();
  const items = NAV.filter((n) => !n.show || role === "admin");

  return (
    <nav
      aria-label="Main"
      className={
        vertical
          ? "flex flex-col gap-1"
          : "flex flex-wrap gap-1 rounded-full border border-line bg-[#0c1018] p-1"
      }
    >
      {items.map(({ href, label, badge }) => {
        const active = pathname !== null && isActive(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-1.5 text-[13px] transition-colors ${
              vertical ? "min-h-11 rounded-lg px-3 text-base" : "rounded-full px-3.5 py-1.5"
            } ${active ? "bg-[#1a2333] font-medium text-ink" : "text-ink-2 hover:text-ink"}`}
          >
            {label}
            {badge === "alerts" && <AlertBadge count={alertCount} />}
          </Link>
        );
      })}
    </nav>
  );
}

/** Sign in / out, and who you are. On laptops (NEXT_PUBLIC_AUTH_DEV=1) a "Sign in as" menu of fake users. */
const noSubscribe = () => () => {};

function Account({ compact = false }: { compact?: boolean }) {
  const { me } = useMe();
  const user = me?.user;
  // localStorage only exists in the browser; the server renders "signed out" and the browser fills it in.
  const currentDevUser = useSyncExternalStore(noSubscribe, devUser, () => null);

  if (DEV_AUTH) {
    return (
      <label className="flex items-center gap-2 rounded-lg border border-dashed border-line px-2 py-1 text-xs text-muted">
        <span className={compact ? "sr-only" : ""}>Sign in as (dev)</span>
        <select
          value={currentDevUser ?? ""}
          onChange={(e) => setDevUser(e.target.value || null)}
          className="max-w-40 rounded-md bg-raised px-2 py-1 text-sm text-ink focus:outline-none"
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

  if (!me) return <div className="h-9 w-20 rounded-lg border border-line" aria-hidden />;
  if (!user) {
    return (
      // A full page load (not <Link>): Auth0's login is a redirect handled by the server.
      <a
        href="/auth/login"
        onClick={(e) => {
          // Come back to the page they were on.
          e.currentTarget.href = signInHref(window.location.pathname + window.location.search);
        }}
        className="flex min-h-9 items-center gap-2 rounded-lg border border-[#2a3446] px-3.5 text-[13px] text-ink hover:border-accent"
      >
        <LogIn className="h-4 w-4 text-accent" aria-hidden />
        Sign in
      </a>
    );
  }
  return (
    <div className="flex items-center gap-2">
      {user.picture ? (
        // eslint-disable-next-line @next/next/no-img-element -- Auth0/Google avatar
        <img src={user.picture} alt="" className="h-8 w-8 rounded-full" referrerPolicy="no-referrer" />
      ) : (
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-sm font-medium text-accent">
          {(user.name ?? user.email ?? "?").slice(0, 1).toUpperCase()}
        </span>
      )}
      {!compact && (
        <span className="min-w-0">
          <span className="block max-w-36 truncate text-sm leading-tight text-ink">{user.name ?? user.email}</span>
          <span className="text-xs text-muted">{ROLE_LABELS[user.role]}</span>
        </span>
      )}
      <a href={SIGN_OUT_HREF} aria-label="Sign out" title="Sign out" className="p-1.5 text-ink-2 hover:text-ink">
        <LogOut className="h-4 w-4" aria-hidden />
      </a>
    </div>
  );
}

function LiveClock() {
  const [label, setLabel] = useState<string | null>(null);
  useEffect(() => {
    const tick = () => setLabel(new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZoneName: "short" }));
    tick();
    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, []);
  return (
    <span className="hidden items-center gap-2 font-mono text-xs tracking-[0.04em] whitespace-nowrap text-ink-2 2xl:flex">
      <span className="live-dot" aria-hidden />
      LIVE{label ? ` · ${label.toUpperCase()}` : ""}
    </span>
  );
}

export function TopNav() {
  const [open, setOpen] = useState(false);
  const alertCount = useAlertCount();

  // While the phone menu is open: Escape closes it and the page behind it doesn't scroll.
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", esc);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <header className="sticky top-0 z-[1050] border-b border-line-soft bg-page/95 backdrop-blur">
      <div className="flex items-center gap-3 px-3 py-2.5 sm:px-6 xl:gap-5">
        <Logo />
        <div className="hidden xl:block">
          <NavLinks />
        </div>
        <div className="flex-1" />
        <LiveClock />
        <Link
          href="/report"
          className="hidden min-h-9 items-center gap-2 rounded-lg bg-accent-strong px-3.5 text-[13px] font-semibold whitespace-nowrap text-on-accent hover:brightness-110 xl:flex"
        >
          <Plus className="h-4 w-4" aria-hidden /> Report hazard
        </Link>
        <Inbox />
        <div className="hidden xl:block">
          <Account compact />
        </div>

        {/* Phones and tablets: alerts, report and a menu button */}
        <Link
          href="/alerts"
          aria-label={`Alerts, ${alertCount} active`}
          className="relative flex h-11 w-11 items-center justify-center text-ink-2 xl:hidden"
        >
          <TriangleAlert className="h-5 w-5" aria-hidden />
          {alertCount > 0 && (
            <span className="absolute top-1 right-0 rounded-full bg-[rgb(245_184_61/0.16)] px-1.5 font-mono text-[10px] text-risk-moderate">
              {alertCount}
            </span>
          )}
        </Link>
        <Link
          href="/report"
          aria-label="Report a hazard"
          className="flex h-11 w-11 items-center justify-center rounded-lg bg-accent-strong text-on-accent xl:hidden"
        >
          <Plus className="h-5 w-5" aria-hidden />
        </Link>
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          className="flex h-11 w-11 items-center justify-center text-ink xl:hidden"
        >
          <Menu className="h-6 w-6" aria-hidden />
        </button>
      </div>

      {/* Rendered into <body>: the header's backdrop blur would otherwise make this "fixed" menu only as tall as
          the header, with the links spilling out below it on no background. */}
      {open &&
        createPortal(
          <div className="fixed inset-0 z-[1200] xl:hidden" role="dialog" aria-modal="true" aria-label="Menu">
            <button type="button" aria-label="Close menu" className="absolute inset-0 bg-black/70" onClick={() => setOpen(false)} />
            <aside className="absolute inset-y-0 right-0 flex w-80 max-w-[88vw] flex-col gap-6 overflow-y-auto border-l border-line bg-card px-4 py-4 shadow-2xl">
              <div className="flex items-center justify-between">
                <span className="eyebrow">Menu</span>
                <button type="button" onClick={() => setOpen(false)} aria-label="Close menu" className="flex h-11 w-11 items-center justify-center text-ink-2">
                  <X className="h-5 w-5" aria-hidden />
                </button>
              </div>
              <SiteSearch onNavigate={() => setOpen(false)} />
              <NavLinks vertical onNavigate={() => setOpen(false)} />
              <div className="mt-auto">
                <Account />
              </div>
            </aside>
          </div>,
          document.body,
        )}
    </header>
  );
}
