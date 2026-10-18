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
  low: "#3fbf7f",
  medium: "#f5b83d",
  high: "#ff4a4a",
};

/** Line-icon paths (24×24, stroked) for the crew-report diamonds on the map, one per hazard type. */
export const HAZARD_ICON_PATHS: Record<HazardType, string> = {
  wildlife:
    "M6 10h.01M10 5.5h.01M14.5 5.5h.01M18.5 10h.01M12 11c3 0 6 4 6 7a3 3 0 0 1-3 3c-1.2 0-2-.6-3-.6s-1.8.6-3 .6a3 3 0 0 1-3-3c0-3 3-7 6-7z",
  flooding: "M3 9c2 0 2-2 4.5-2S10 9 12 9s2-2 4.5-2S19 9 21 9M3 15c2 0 2-2 4.5-2S10 15 12 15s2-2 4.5-2S19 15 21 15",
  unstable_ground: "M12 3l6 17H6zM8.5 13h7M7.5 16.5h9",
  downed_line: "M13 2L4 14h7l-1 8 9-12h-7z",
  heat_illness: "M14 14.8V4a2 2 0 0 0-4 0v10.8a4 4 0 1 0 4 0z",
  fire: "M12 3c1 3 5 5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-4 2.5-5 0 2 1 3 2.5 3 0-3-1.5-5 0-8z",
  other: "M12 4v10M12 19h.01",
};
