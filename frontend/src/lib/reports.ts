import {
  Activity,
  CircleDashed,
  CloudLightning,
  CloudSnow,
  FlaskConical,
  Flame,
  Haze,
  HeartPulse,
  Mountain,
  PawPrint,
  Snowflake,
  ThermometerSnowflake,
  TreePine,
  TriangleAlert,
  Waves,
  Wind,
  Zap,
  type LucideIcon,
} from "lucide-react";
import type { HazardType, ReportSeverity } from "./api";

/** One icon per crew report type (the report form's buttons and report lists). */
export const HAZARD_ICONS: Record<HazardType, LucideIcon> = {
  lightning: CloudLightning,
  flooding: Waves,
  high_wind: Wind,
  heat_illness: HeartPulse,
  cold_stress: ThermometerSnowflake,
  ice: Snowflake,
  snow: CloudSnow,
  smoke: Haze,
  fire: Flame,
  wildlife: PawPrint,
  downed_line: Zap,
  fallen_tree: TreePine,
  unstable_ground: Mountain,
  sinkhole: CircleDashed,
  earthquake_damage: Activity,
  gas_leak: FlaskConical,
  other: TriangleAlert,
};

export const HAZARD_LABELS: Record<HazardType, string> = {
  wildlife: "Wildlife",
  flooding: "Flooding",
  unstable_ground: "Soft ground",
  downed_line: "Downed line",
  heat_illness: "Heat illness",
  fire: "Fire",
  other: "Other hazard",
  lightning: "Lightning / thunder",
  high_wind: "High wind",
  ice: "Ice",
  snow: "Snow / drifts",
  cold_stress: "Cold stress",
  smoke: "Smoke",
  sinkhole: "Sinkhole / washout",
  fallen_tree: "Fallen tree / debris",
  gas_leak: "Gas leak / spill",
  earthquake_damage: "Quake damage",
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
  lightning: "🌩️",
  high_wind: "💨",
  ice: "🧊",
  snow: "❄️",
  cold_stress: "🥶",
  smoke: "🌫️",
  sinkhole: "🕳️",
  fallen_tree: "🌳",
  gas_leak: "☣️",
  earthquake_damage: "🏚️",
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
  lightning: "M16 13a4 4 0 0 0 0-8 6 6 0 0 0-11.5 2A3.5 3.5 0 0 0 5 13M13 11l-3 5h4l-3 5",
  high_wind: "M3 8h11a3 3 0 1 0-3-3M3 12h15a3 3 0 1 1-3 3M3 16h7",
  ice: "M12 2v20M4 7l16 10M4 17L20 7M9 3.5l3 2 3-2M9 20.5l3-2 3 2",
  snow: "M17 15a4 4 0 0 0 0-8 6 6 0 0 0-11.5 2A3.5 3.5 0 0 0 6 15zM8 19h.01M12 21h.01M16 19h.01",
  cold_stress: "M10 13.8V4a2 2 0 0 1 4 0v9.8a4 4 0 1 1-4 0zM19 3v6M16.5 4.5l5 3M21.5 4.5l-5 3",
  smoke: "M4 8h12M2 12h18M6 16h12M4 20h10",
  sinkhole: "M3 12c0-2 4-4 9-4s9 2 9 4-4 4-9 4-9-2-9-4zM7 12c1.3 1 3 1.5 5 1.5s3.7-.5 5-1.5",
  fallen_tree: "M3 20h18M5 18L17 8M14 5a3.5 3.5 0 1 1 5 5",
  gas_leak: "M9 3h6M10 3v6L5 19a1.5 1.5 0 0 0 1.3 2h11.4a1.5 1.5 0 0 0 1.3-2L14 9V3M7.5 15h9",
  earthquake_damage: "M2 12h4l3-8 4 16 3-8h6",
};
