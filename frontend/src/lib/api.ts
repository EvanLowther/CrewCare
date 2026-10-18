// Typed client for the Crew Care API. Types come from src/lib/api-types.ts,
// which is generated from backend/planit/models.py (run `python dev.py types`, never edit it by hand).
import type { components } from "./api-types";
import { authHeaders } from "./auth";

export type S = components["schemas"];
export type SiteSummary = S["SiteSummary"];
export type SiteList = S["SiteList"];
export type SiteDetail = S["SiteDetail"];
export type Alert = S["Alert"];
export type AlertList = S["AlertList"];
export type HazardReport = S["HazardReport"];
export type ReportList = S["ReportList"];
export type Briefing = S["Briefing"];
export type BriefingList = S["BriefingList"];
export type Risk = S["Risk"];
export type RiskPoint = S["RiskPoint"];
export type RiskLevel = Risk["level"];
export type Conditions = S["Conditions"];
export type Health = S["Health"];
export type HazardType = HazardReport["hazard_type"];
export type ReportSeverity = HazardReport["severity"];
export type Me = S["Me"];
export type User = S["User"];
export type UserRole = User["role"];
export type SiteRole = S["SiteMember"]["role"];
export type SiteMember = S["SiteMember"];
export type AdminUser = S["AdminUser"];
export type SiteCreate = S["SiteCreate"];
export type SiteUpdate = S["SiteUpdate"];
export type Notification = S["Notification"];
export type NotificationList = S["NotificationList"];
export type LocationHistory = S["LocationHistory"];
export type PastReport = S["PastReport"];
export type PastStormEvent = S["PastStormEvent"];
/** Whose risk scores to show: the XGBoost model or rules-v2 (both are stored for every site-hour). */
export type Scorer = "ml" | "rules";

// Same-origin: next.config.ts forwards /api/* to FastAPI (on the server, Caddy sends it straight there).
export const API_URL = "";

/** An API error whose message is the API's own explanation (FastAPI's `detail`), ready to show to the user. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const DEV = process.env.NODE_ENV === "development";

/** What to say when the API gave no explanation of its own (a crash, or a proxy error page). */
function fallbackMessage(status: number): string {
  if (status === 0 || status === 502 || status === 504) {
    return DEV ? "Can't reach the API. Is python dev.py api running?" : "Can't reach the server right now.";
  }
  if (status === 503) return "The server is busy. Try again in a moment.";
  if (status >= 500) return "Something went wrong on the server. Try again, and tell an admin if it keeps happening.";
  return `Request failed (${status})`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      cache: "no-store",
      headers: { ...(await authHeaders()), ...(body === undefined || isForm ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, fallbackMessage(0));
  }
  if (!res.ok) {
    // FastAPI explains refusals in `detail` (JSON). Anything else (a crash's "Internal Server Error", a proxy's HTML
    // page) isn't worth showing as is.
    let detail: string | null = null;
    try {
      const parsed = JSON.parse(await res.text()).detail;
      detail = typeof parsed === "string" ? parsed : Array.isArray(parsed) ? parsed.map((d) => d.msg).join("; ") : null;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail || fallbackMessage(res.status));
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const get = <T>(path: string) => request<T>("GET", path);
const post = <T>(path: string, body?: unknown) => request<T>("POST", path, body);

export const api = {
  health: () => get<Health>("/api/health"),
  sites: (model?: Scorer) => get<SiteList>(`/api/sites${model ? `?model=${model}` : ""}`),
  site: (id: number, model?: Scorer) => get<SiteDetail>(`/api/sites/${id}${model ? `?model=${model}` : ""}`),
  alerts: (opts: { siteId?: number; since?: string } = {}) => {
    const q = new URLSearchParams();
    if (opts.siteId !== undefined) q.set("site_id", String(opts.siteId));
    if (opts.since) q.set("since", opts.since);
    return get<AlertList>(`/api/alerts${q.size ? `?${q}` : ""}`);
  },
  /** Active reports; with a site and `includePast`, its resolved and expired ones too. */
  reports: (siteId?: number, includePast = false) =>
    get<ReportList>(
      `/api/reports${siteId !== undefined ? `?site_id=${siteId}${includePast ? "&include_past=true" : ""}` : ""}`,
    ),
  createReport: (form: {
    site_id: number;
    latitude: number;
    longitude: number;
    gps_latitude?: number;
    gps_longitude?: number;
    gps_accuracy_m?: number;
    hazard_type: HazardType;
    severity: ReportSeverity;
    description?: string;
    photo?: File;
  }) => {
    const body = new FormData();
    for (const [k, v] of Object.entries(form)) if (v !== undefined) body.append(k, v instanceof File ? v : String(v));
    return post<HazardReport>("/api/reports", body);
  },
  resolveReport: (id: string) => request<HazardReport>("PATCH", `/api/reports/${id}/resolve`),
  photoUrl: (relative: string) => `${API_URL}${relative}`,
  briefings: (forDate?: string) => get<BriefingList>(`/api/briefings${forDate ? `?for_date=${forDate}` : ""}`),
  generateBriefings: () => post<S["DemoAck"]>("/api/briefings/generate"),
  lightningReplay: (req: S["LightningReplayRequest"]) => post<S["DemoAck"]>("/api/demo/lightning-replay", req),

  // Login, sites and members (docs/AUTH.md)
  me: () => get<Me>("/api/me"),
  createSite: (req: SiteCreate) => post<SiteDetail>("/api/sites", req),
  updateSite: (id: number, req: SiteUpdate) => request<SiteDetail>("PATCH", `/api/sites/${id}`, req),
  deleteSite: (id: number) => request<void>("DELETE", `/api/sites/${id}`),
  members: (siteId: number) => get<S["SiteMemberList"]>(`/api/sites/${siteId}/members`),
  addMember: (siteId: number, userId: string, role: SiteRole) =>
    post<S["SiteMemberList"]>(`/api/sites/${siteId}/members`, { user_id: userId, role }),
  removeMember: (siteId: number, userId: string) =>
    request<S["SiteMemberList"]>("DELETE", `/api/sites/${siteId}/members/${userId}`),
  searchUsers: (q: string) => get<S["UserList"]>(`/api/users?q=${encodeURIComponent(q)}`),
  geocode: (q: string) => get<S["GeocodeList"]>(`/api/geocode?q=${encodeURIComponent(q)}`),
  adminUsers: () => get<S["AdminUserList"]>("/api/admin/users"),
  setRole: (userId: string, role: UserRole) => request<AdminUser>("PATCH", `/api/admin/users/${userId}`, { role }),

  // Notifications and push (crew reports, danger alerts and briefings on your sites)
  notifications: () => get<NotificationList>("/api/notifications"),
  markRead: (ids?: number[]) => post<NotificationList>("/api/notifications/read", ids ? { ids } : {}),
  pushKey: () => get<S["PushKey"]>("/api/notifications/push-key"),
  subscribePush: (sub: S["PushSubscriptionIn"]) => post<void>("/api/notifications/subscriptions", sub),
  unsubscribePush: (endpoint: string) => post<void>("/api/notifications/subscriptions/delete", { endpoint }),

  // Past hazards near a site, or any spot (new-site form)
  siteHistory: (siteId: number) => get<LocationHistory>(`/api/sites/${siteId}/history`),
  placeHistory: (lat: number, lon: number) =>
    get<LocationHistory>(`/api/history?lat=${lat.toFixed(5)}&lon=${lon.toFixed(5)}`),
};

/**
 * Reads /api/notifications/stream (server-sent events) with fetch, since EventSource can't send the sign-in
 * token. Calls `onNotification` for each new one and resolves when the server ends the stream (every couple of
 * minutes) or `signal` aborts; rejects if it can't connect.
 */
export async function streamNotifications(
  after: number | null,
  onNotification: (n: Notification) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/notifications/stream${after !== null ? `?after=${after}` : ""}`, {
    headers: { ...(await authHeaders()), Accept: "text/event-stream" },
    cache: "no-store",
    signal,
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, fallbackMessage(res.status));
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const event = block.match(/^event: (.*)$/m)?.[1];
      const data = block.match(/^data: (.*)$/m)?.[1];
      if (event === "notification" && data) onNotification(JSON.parse(data) as Notification);
    }
  }
}
