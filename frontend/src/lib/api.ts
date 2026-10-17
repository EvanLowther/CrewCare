// Typed client for the PlanIT API. Types come from src/lib/api-types.ts,
// which is generated from backend/planit/models.py (run `python dev.py types`, never edit it by hand).
import type { components } from "./api-types";

type S = components["schemas"];
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
export type RiskLevel = Risk["level"];
export type Conditions = S["Conditions"];
export type Health = S["Health"];
export type HazardType = HazardReport["hazard_type"];
export type ReportSeverity = HazardReport["severity"];

// Same-origin: next.config.ts forwards /api/* to FastAPI.
export const API_URL = "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${path}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${path}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<Health>("/api/health"),
  sites: () => get<SiteList>("/api/sites"),
  site: (id: number) => get<SiteDetail>(`/api/sites/${id}`),
  alerts: (opts: { siteId?: number; since?: string } = {}) => {
    const q = new URLSearchParams();
    if (opts.siteId !== undefined) q.set("site_id", String(opts.siteId));
    if (opts.since) q.set("since", opts.since);
    return get<AlertList>(`/api/alerts${q.size ? `?${q}` : ""}`);
  },
  reports: (siteId?: number) => get<ReportList>(`/api/reports${siteId !== undefined ? `?site_id=${siteId}` : ""}`),
  createReport: async (form: {
    latitude: number;
    longitude: number;
    hazard_type: HazardType;
    severity: ReportSeverity;
    description?: string;
    reporter_name?: string;
    photo?: File;
  }) => {
    const body = new FormData();
    for (const [k, v] of Object.entries(form)) if (v !== undefined) body.append(k, v instanceof File ? v : String(v));
    const res = await fetch(`${API_URL}/api/reports`, { method: "POST", body });
    if (!res.ok) throw new Error(`${res.status} POST /api/reports: ${await res.text()}`);
    return (await res.json()) as HazardReport;
  },
  photoUrl: (relative: string) => `${API_URL}${relative}`,
  briefings: (forDate?: string) => get<BriefingList>(`/api/briefings${forDate ? `?for_date=${forDate}` : ""}`),
  generateBriefings: () => post<S["DemoAck"]>("/api/briefings/generate"),
  lightningReplay: (req: S["LightningReplayRequest"]) => post<S["DemoAck"]>("/api/demo/lightning-replay", req),
};
