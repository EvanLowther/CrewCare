"use client";

import { Bell, BellRing, FileText, MapPin, Smartphone, TriangleAlert, X, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, streamNotifications, type Notification } from "@/lib/api";
import { SEVERITY_STYLES } from "@/lib/alerts";
import { relativeTime } from "@/lib/format";
import { disablePush, enablePush, isIos, pushState, refreshPushSubscription, type PushState } from "@/lib/push";
import { useMe } from "./MeProvider";

// Crew reports, danger alerts and briefings on the sites you're on (written by database triggers, migration 011).
// While a page is open they arrive over a live stream within ~2 s and pop up as toasts; when the tab is in the
// background, as a desktop notification; with push turned on, on the phone even when the site is closed.

const KIND_ICONS: Record<Notification["kind"], LucideIcon> = {
  crew_report: MapPin,
  alert: TriangleAlert,
  briefing: FileText,
};

type State = {
  items: Notification[];
  unread: number;
  markRead: (ids?: number[]) => void;
  push: PushState | null;
  setPush: (enable: boolean) => Promise<void>;
  pushError: string | null;
  clearToasts: () => void;
};

const Ctx = createContext<State>({
  items: [],
  unread: 0,
  markRead: () => {},
  push: null,
  setPush: async () => {},
  pushError: null,
  clearToasts: () => {},
});

export function useNotifications() {
  return useContext(Ctx);
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function NotificationsProvider({ children }: { children: React.ReactNode }) {
  const { me } = useMe();
  const userId = me?.user?.id ?? null;
  const router = useRouter();
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [toasts, setToasts] = useState<Notification[]>([]);
  const [push, setPushState] = useState<PushState | null>(null);
  const [pushError, setPushError] = useState<string | null>(null);
  const pushRef = useRef<PushState | null>(null);
  useEffect(() => {
    pushRef.current = push;
  }, [push]);

  const arrived = useCallback(
    (n: Notification) => {
      setItems((prev) => [n, ...prev.filter((x) => x.id !== n.id)].slice(0, 50));
      setUnread((u) => u + 1);
      setToasts((prev) => [n, ...prev.filter((x) => x.id !== n.id)].slice(0, 4));
      // Tab in the background and no push on this device (push already shows it): a desktop notification.
      if (document.hidden && pushRef.current !== "on" && "Notification" in window && Notification.permission === "granted") {
        const shown = new window.Notification(n.title, { body: n.body ?? "", tag: `crewcare-${n.id}`, icon: "/icon-192.png" });
        shown.onclick = () => {
          window.focus();
          if (n.link) router.push(n.link);
          shown.close();
        };
      }
    },
    [router],
  );

  // Load the inbox, then keep a live stream open (it reconnects every couple of minutes, and after errors).
  useEffect(() => {
    if (!userId) {
      // Signed out (or switched user): nothing to show until the new user's list loads.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setItems([]);
      setUnread(0);
      return;
    }
    const ctrl = new AbortController();
    let last: number | null = null;
    const catchUp = async () => {
      const list = await api.notifications();
      if (ctrl.signal.aborted) return;
      if (last === null) {
        setItems(list.notifications);
      } else {
        for (const n of [...list.notifications].reverse()) if (n.id > last) arrived(n);
      }
      setUnread(list.unread);
      last = Math.max(last ?? 0, list.notifications[0]?.id ?? 0);
    };
    (async () => {
      await catchUp().catch(() => {});
      refreshPushSubscription();
      let delay = 1000;
      while (!ctrl.signal.aborted) {
        try {
          await streamNotifications(last, (n) => {
            last = Math.max(last ?? 0, n.id);
            arrived(n);
          }, ctrl.signal);
          delay = 1000;
        } catch {
          if (ctrl.signal.aborted) return;
          await sleep(delay);
          delay = Math.min(delay * 2, 30_000);
          await catchUp().catch(() => {});
        }
      }
    })();
    return () => ctrl.abort();
  }, [userId, arrived]);

  useEffect(() => {
    pushState().then(setPushState, () => setPushState("unsupported"));
  }, []);

  const markRead = useCallback((ids?: number[]) => {
    setItems((prev) => prev.map((n) => (!ids || ids.includes(n.id) ? { ...n, read: true } : n)));
    api.markRead(ids).then((list) => setUnread(list.unread), () => {});
  }, []);

  const setPush = useCallback(async (enable: boolean) => {
    setPushError(null);
    try {
      setPushState(enable ? await enablePush() : await disablePush());
    } catch (e) {
      setPushError(e instanceof Error ? e.message : "Couldn't turn on notifications");
      setPushState(await pushState());
    }
  }, []);

  const clearToasts = useCallback(() => setToasts([]), []);
  const value = useMemo(
    () => ({ items, unread, markRead, push, setPush, pushError, clearToasts }),
    [items, unread, markRead, push, setPush, pushError, clearToasts],
  );
  const dismiss = (id: number) => setToasts((prev) => prev.filter((t) => t.id !== id));

  return (
    <Ctx.Provider value={value}>
      {children}
      <Toasts toasts={toasts} onDismiss={dismiss} onOpen={(n) => markRead([n.id])} />
    </Ctx.Provider>
  );
}

function Toasts({ toasts, onDismiss, onOpen }: { toasts: Notification[]; onDismiss: (id: number) => void; onOpen: (n: Notification) => void }) {
  return (
    <div aria-live="polite" className="pointer-events-none fixed inset-x-3 top-16 z-[1300] flex flex-col items-end gap-2 sm:left-auto sm:right-5 sm:w-96">
      {toasts.map((n) => (
        <Toast key={n.id} n={n} onDismiss={() => onDismiss(n.id)} onOpen={() => onOpen(n)} />
      ))}
    </div>
  );
}

function Toast({ n, onDismiss, onOpen }: { n: Notification; onDismiss: () => void; onOpen: () => void }) {
  // Danger stays until closed; the rest fade after 10 s.
  useEffect(() => {
    if (n.severity === "danger") return;
    const t = setTimeout(onDismiss, 10_000);
    return () => clearTimeout(t);
  }, [n.severity, onDismiss]);
  const Icon = KIND_ICONS[n.kind];
  const style = SEVERITY_STYLES[n.severity];
  return (
    <div
      role={n.severity === "danger" ? "alert" : "status"}
      className="pointer-events-auto flex w-full gap-3 rounded-xl border bg-raised p-3 shadow-2xl"
      style={{ borderColor: style.dot }}
    >
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg" style={{ background: style.bg, color: style.fg }}>
        <Icon className="h-4 w-4" aria-hidden />
      </span>
      <Link
        href={n.link ?? "/"}
        onClick={() => {
          onOpen();
          onDismiss();
        }}
        className="min-w-0 flex-1"
      >
        <p className="text-sm font-semibold text-ink">{n.title}</p>
        {n.body && <p className="mt-0.5 line-clamp-2 text-xs text-ink-2">{n.body}</p>}
      </Link>
      <button type="button" onClick={onDismiss} aria-label="Dismiss" className="-m-1 h-8 w-8 shrink-0 p-1.5 text-muted hover:text-ink">
        <X className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}

/** The bell in the top bar: unread count, your recent notifications, and turning push on for this device. */
export function Inbox() {
  const { signedIn } = useMe();
  const { items, unread, markRead, clearToasts } = useNotifications();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  if (!signedIn) return null;
  return (
    <div ref={box} className="relative">
      <button
        type="button"
        onClick={() => {
          // The open list shows the same things; pop-ups on top of it only get in the way.
          if (!open) clearToasts();
          setOpen(!open);
        }}
        aria-expanded={open}
        aria-label={`Notifications, ${unread} unread`}
        className="relative flex h-11 w-11 items-center justify-center text-ink-2 hover:text-ink xl:h-9 xl:w-9"
      >
        {unread > 0 ? <BellRing className="h-5 w-5 text-accent" aria-hidden /> : <Bell className="h-5 w-5" aria-hidden />}
        {unread > 0 && (
          <span className="absolute top-0.5 right-0 rounded-full bg-risk-extreme px-1.5 font-mono text-[10px] leading-4 font-semibold text-on-accent xl:-top-1 xl:-right-1">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="fixed inset-x-3 top-16 z-[1250] flex max-h-[75vh] flex-col overflow-hidden rounded-xl border border-line bg-raised shadow-2xl sm:absolute sm:inset-x-auto sm:top-full sm:right-0 sm:mt-2 sm:w-96">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <span className="text-sm font-semibold text-ink">Notifications</span>
            {unread > 0 && (
              <button type="button" onClick={() => markRead()} className="text-xs text-accent hover:underline">
                Mark all read
              </button>
            )}
          </div>
          <PushToggle />
          <ul className="min-h-0 flex-1 divide-y divide-line overflow-y-auto">
            {items.length === 0 ? (
              <li className="px-4 py-8 text-center text-sm text-muted">
                Nothing yet. Crew reports, danger alerts and the 6 PM briefing for your sites show up here.
              </li>
            ) : (
              items.map((n) => {
                const Icon = KIND_ICONS[n.kind];
                return (
                  <li key={n.id}>
                    <Link
                      href={n.link ?? "/"}
                      onClick={() => {
                        if (!n.read) markRead([n.id]);
                        setOpen(false);
                      }}
                      className={`flex gap-3 px-4 py-3 hover:bg-card ${n.read ? "" : "bg-accent-soft/40"}`}
                    >
                      <span
                        className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md"
                        style={{ background: SEVERITY_STYLES[n.severity].bg, color: SEVERITY_STYLES[n.severity].fg }}
                      >
                        <Icon className="h-3.5 w-3.5" aria-hidden />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className={`block text-sm ${n.read ? "text-ink-2" : "font-medium text-ink"}`}>{n.title}</span>
                        {n.body && <span className="mt-0.5 line-clamp-2 block text-xs text-muted">{n.body}</span>}
                        <span className="mt-1 block text-[11px] text-muted">{relativeTime(n.created_at)}</span>
                      </span>
                      {!n.read && <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-accent" aria-label="Unread" />}
                    </Link>
                  </li>
                );
              })
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

function PushToggle() {
  const { push, setPush, pushError } = useNotifications();
  const [busy, setBusy] = useState(false);
  if (push === null || push === "unsupported") return null;
  const toggle = async (enable: boolean) => {
    setBusy(true);
    await setPush(enable);
    setBusy(false);
  };
  let text: string;
  let action: React.ReactNode = null;
  if (push === "needs-home-screen") {
    text = "To get these on your iPhone, tap Share, then \"Add to Home Screen\", and open Crew Care from there.";
  } else if (push === "denied") {
    text = `Notifications are blocked for this site. Allow them in your ${isIos() ? "iPhone Settings" : "browser's site settings"}.`;
  } else if (push === "on") {
    text = "Notifications are on for this device.";
    action = (
      <button type="button" disabled={busy} onClick={() => toggle(false)} className="text-xs text-muted hover:text-ink">
        Turn off
      </button>
    );
  } else {
    text = "Get these on this device, even when Crew Care is closed.";
    action = (
      <button
        type="button"
        disabled={busy}
        onClick={() => toggle(true)}
        className="shrink-0 rounded-lg bg-accent-strong px-3 py-1.5 text-xs font-semibold text-on-accent disabled:opacity-60"
      >
        {busy ? "Turning on…" : "Turn on"}
      </button>
    );
  }
  return (
    <div className="border-b border-line px-4 py-3">
      <div className="flex items-center gap-3">
        <Smartphone className="h-4 w-4 shrink-0 text-accent" aria-hidden />
        <p className="flex-1 text-xs text-ink-2">{text}</p>
        {action}
      </div>
      {pushError && <p className="mt-2 text-xs text-[#ff9b9b]">{pushError}</p>}
    </div>
  );
}
