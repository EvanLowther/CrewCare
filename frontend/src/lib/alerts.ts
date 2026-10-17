import type { Alert } from "./api";

type AlertType = Alert["type"];

export const ALERT_ICONS: Record<AlertType, string> = {
  lightning: "⚡",
  flood: "🌊",
  heat: "🌡️",
  storm: "⛈️",
  wind: "💨",
  wildfire: "🔥",
  crew_report: "📍",
  nws: "⚠️",
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
