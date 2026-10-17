import type { HazardType, ReportSeverity } from "./api";

export const HAZARD_LABELS: Record<HazardType, string> = {
  wildlife: "Wildlife",
  flooding: "Flooding",
  unstable_ground: "Soft ground",
  downed_line: "Downed line",
  heat_illness: "Heat illness",
  fire: "Fire",
  other: "Other hazard",
};

/** Plain-text icons for Leaflet markers (HTML strings). */
export const HAZARD_EMOJI: Record<HazardType, string> = {
  wildlife: "🐊",
  flooding: "🌊",
  unstable_ground: "🚧",
  downed_line: "⚡",
  heat_illness: "🥵",
  fire: "🔥",
  other: "⚠️",
};

export const REPORT_SEVERITY_COLORS: Record<ReportSeverity, string> = {
  low: "#0ca30c",
  medium: "#fab219",
  high: "#d03b3b",
};
