import {
  Activity,
  CloudLightning,
  Flame,
  Haze,
  MapPin,
  ThermometerSun,
  TriangleAlert,
  Waves,
  Wind,
  Zap,
  type LucideIcon,
} from "lucide-react";
import type { Alert } from "./api";

type AlertType = Alert["type"];
type Severity = Alert["severity"];

/** Plain-text icons for places that take HTML strings (Leaflet map pins). */
export const ALERT_EMOJI: Record<AlertType, string> = {
  lightning: "⚡",
  flood: "🌊",
  heat: "🌡️",
  storm: "⛈️",
  wind: "💨",
  wildfire: "🔥",
  air_quality: "🌫️",
  earthquake: "🌐",
  crew_report: "📍",
  nws: "⚠️",
};

export const ALERT_ICONS: Record<AlertType, LucideIcon> = {
  lightning: Zap,
  flood: Waves,
  heat: ThermometerSun,
  storm: CloudLightning,
  wind: Wind,
  wildfire: Flame,
  air_quality: Haze,
  earthquake: Activity,
  crew_report: MapPin,
  nws: TriangleAlert,
};

export const ALERT_LABELS: Record<AlertType, string> = {
  lightning: "Lightning",
  flood: "Flood risk",
  heat: "Extreme heat",
  storm: "Severe storm",
  wind: "High wind",
  wildfire: "Wildfire",
  air_quality: "Smoke / air quality",
  earthquake: "Earthquake",
  crew_report: "Crew report",
  nws: "NWS alert",
};

export const SEVERITY_LABELS: Record<Severity, string> = { danger: "Danger", warning: "Warning", info: "Info" };

/** Badge colors: tinted fill + readable text, matching the risk palette's red / amber / ice blue; the dot is also the map ring color. */
export const SEVERITY_STYLES: Record<Severity, { bg: string; fg: string; dot: string }> = {
  danger: { bg: "rgb(255 74 74 / 0.14)", fg: "#ff8a8a", dot: "#ff4a4a" },
  warning: { bg: "rgb(245 184 61 / 0.14)", fg: "#ffd27a", dot: "#f5b83d" },
  info: { bg: "rgb(154 215 255 / 0.12)", fg: "#bfe6ff", dot: "#9ad7ff" },
};

export const SEVERITY_RANK: Record<Severity, number> = { danger: 0, warning: 1, info: 2 };

/** The alert's heading: its type, or for a generic NWS alert the NWS event itself ("Winter Storm Warning"). */
export function alertLabel(alert: Pick<Alert, "type" | "meta">): string {
  const event = alert.type === "nws" ? (alert.meta as { nws_event?: string }).nws_event : undefined;
  return event ?? ALERT_LABELS[alert.type];
}

/** When the alert stops on its own: lightning's all-clear, or an NWS / earthquake alert's end time. */
export function alertEndsAt(alert: Pick<Alert, "all_clear_at" | "meta">): string | null {
  return alert.all_clear_at ?? (alert.meta as { ends?: string | null }).ends ?? null;
}

/** Still in force at `now` (ms). The API already drops ended alerts; this hides one the moment it ends between polls. */
export function inForce(alert: Pick<Alert, "status" | "all_clear_at" | "meta">, now: number): boolean {
  const ends = alertEndsAt(alert);
  return alert.status === "active" && (ends === null || new Date(ends).getTime() > now);
}
