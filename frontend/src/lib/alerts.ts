import {
  CloudLightning,
  Flame,
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
  crew_report: "Crew report",
  nws: "NWS alert",
};

export const SEVERITY_LABELS: Record<Severity, string> = { danger: "Danger", warning: "Warning", info: "Info" };

/** Badge colors: tinted fill + readable text, matching the risk palette's red / amber / blue. */
export const SEVERITY_STYLES: Record<Severity, { bg: string; fg: string; dot: string }> = {
  danger: { bg: "rgb(208 59 59 / 0.16)", fg: "#ff8a8a", dot: "#d03b3b" },
  warning: { bg: "rgb(250 178 25 / 0.14)", fg: "#fcc954", dot: "#fab219" },
  info: { bg: "rgb(110 123 255 / 0.16)", fg: "#a5adff", dot: "#6e7bff" },
};

export const SEVERITY_RANK: Record<Severity, number> = { danger: 0, warning: 1, info: 2 };
