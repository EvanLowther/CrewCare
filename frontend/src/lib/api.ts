// Typed client for the PlanIT API. Types come from src/lib/api-types.ts,
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

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const res = await fetch(`${API_URL}${path}`, {
    method,
    cache: "no-store",
    headers: { ...(await authHeaders()), ...(body === undefined || isForm ? {} : { "Content-Type": "application/json" }) },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const parsed = JSON.parse(text).detail;
      detail = typeof parsed === "string" ? parsed : Array.isArray(parsed) ? parsed.map((d) => d.msg).join("; ") : text;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail || `${res.status} ${method} ${path}`);
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
  reports: (siteId?: number) => get<ReportList>(`/api/reports${siteId !== undefined ? `?site_id=${siteId}` : ""}`),
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
};
