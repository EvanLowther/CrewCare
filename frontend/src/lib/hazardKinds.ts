// What kind of hazard a risk factor or alert is, with its icon and colour, so smoke, wildfire, earthquakes, winter
// weather and cold look different wherever factors and alerts are listed.
//
// Colour is a family, not an identity: warm (heat, fire, smoke), water (rain, flood, storms) and ice (cold, snow,
// ice), checked for colour-blind separation on the dark page. Everything else is neutral. The icon and the text
// label always say the exact kind, so colour is never the only cue.
import {
  Activity,
  CalendarDays,
  CloudFog,
  CloudLightning,
  CloudRain,
  Droplets,
  Flame,
  Haze,
  MapPin,
  Mountain,
  Snowflake,
  ThermometerSnowflake,
  ThermometerSun,
  TriangleAlert,
  Waves,
  Wind,
  Zap,
  type LucideIcon,
} from "lucide-react";
import type { Alert, HazardType } from "./api";
import { HAZARD_ICONS } from "./reports";

export type HazardKind =
  | "heat"
  | "cold"
  | "winter"
  | "wind"
  | "lightning"
  | "storm"
  | "rain"
  | "flood"
  | "ground"
  | "visibility"
  | "wildfire"
  | "smoke"
  | "earthquake"
  | "crew_report"
  | "location"
  | "season"
  | "other";

const WARM = "#d95926";
const WATER = "#3987e5";
const ICE = "#199e70";
const NEUTRAL = "#8a93a6";

export const HAZARD_KINDS: Record<HazardKind, { label: string; icon: LucideIcon; color: string }> = {
  heat: { label: "Heat", icon: ThermometerSun, color: WARM },
  wildfire: { label: "Wildfire", icon: Flame, color: WARM },
  smoke: { label: "Smoke", icon: Haze, color: WARM },
  lightning: { label: "Lightning", icon: Zap, color: WATER },
  storm: { label: "Storms", icon: CloudLightning, color: WATER },
  rain: { label: "Heavy rain", icon: CloudRain, color: WATER },
  flood: { label: "Flooding", icon: Waves, color: WATER },
  ground: { label: "Soggy ground", icon: Droplets, color: WATER },
  cold: { label: "Cold", icon: ThermometerSnowflake, color: ICE },
  winter: { label: "Snow and ice", icon: Snowflake, color: ICE },
  wind: { label: "Wind", icon: Wind, color: NEUTRAL },
  visibility: { label: "Low visibility", icon: CloudFog, color: NEUTRAL },
  earthquake: { label: "Earthquake", icon: Activity, color: NEUTRAL },
  crew_report: { label: "Crew report", icon: MapPin, color: NEUTRAL },
  location: { label: "Location", icon: Mountain, color: NEUTRAL },
  season: { label: "Time of year", icon: CalendarDays, color: NEUTRAL },
  other: { label: "Other", icon: TriangleAlert, color: NEUTRAL },
};

/** Risk factor key (backend/planit/hazards.py and ml/model.py FACTOR_LABELS) -> kind. */
const FACTOR_KINDS: Record<string, HazardKind> = {
  heat_index: "heat",
  dry_air: "heat",
  cold: "cold",
  wind_chill: "cold",
  snow: "winter",
  snow_depth: "winter",
  ice: "winter",
  wind: "wind",
  lightning: "lightning",
  thunderstorm: "storm",
  downpour: "rain",
  rain_24h: "rain",
  rain_3d: "rain",
  soil_moisture: "ground",
  visibility: "visibility",
  smoke: "smoke",
  fire_weather: "wildfire",
  location: "location",
  season: "season",
};

/** App alert type -> kind. `nws` alerts are refined by their NWS event name (see alertKind). */
const ALERT_TYPE_KINDS: Record<Alert["type"], HazardKind> = {
  lightning: "lightning",
  flood: "flood",
  heat: "heat",
  storm: "storm",
  wind: "wind",
  wildfire: "wildfire",
  air_quality: "smoke",
  earthquake: "earthquake",
  crew_report: "crew_report",
  nws: "other",
};

// NWS event names (alerts that arrive as the generic `nws` type) and NOAA Storm Events types, matched in order.
const NWS_EVENT_KINDS: [RegExp, HazardKind][] = [
  [/lightning/i, "lightning"],
  [/hail|funnel|waterspout/i, "storm"],
  [/winter|snow|blizzard|ice storm|freezing (rain|spray|fog)|sleet|lake.effect/i, "winter"],
  [/cold|chill|freeze|frost/i, "cold"],
  [/fog|smoke|dust|ashfall/i, "visibility"],
  [/heat/i, "heat"],
  [/flood|surge|tsunami|hydrologic/i, "flood"],
  [/thunderstorm|tornado|hurricane|tropical/i, "storm"],
  [/wind|gale|marine/i, "wind"],
  [/fire|red flag/i, "wildfire"],
  [/air quality/i, "smoke"],
  [/earthquake/i, "earthquake"],
];

/** Kind of an NWS alert event or a NOAA Storm Events type ("Thunderstorm Wind", "Flash Flood", ...). */
export function eventKind(event: string): HazardKind {
  return nwsKind(event);
}

function nwsKind(event: string): HazardKind {
  return NWS_EVENT_KINDS.find(([re]) => re.test(event))?.[1] ?? "other";
}

/** `label` matters for NWS alert factors (key "alert_nws"), whose label is the NWS event ("Freeze Warning"). */
// Crew report factors ("report_<type>", backend/planit/hazards.py crew_report) -> the danger they share a kind with.
const REPORT_KINDS: Partial<Record<HazardType, HazardKind>> = {
  flooding: "flood",
  fire: "wildfire",
  lightning: "lightning",
  high_wind: "wind",
  heat_illness: "heat",
  ice: "winter",
  snow: "winter",
  cold_stress: "cold",
  smoke: "smoke",
  earthquake_damage: "earthquake",
};

function reportType(key: string): HazardType | null {
  const type = key.startsWith("report_") ? key.slice("report_".length) : null;
  return type && type in HAZARD_ICONS ? (type as HazardType) : null;
}

/** The icon for a risk factor: a crew report shows its report type's own icon (paw for wildlife, ...). */
export function factorIcon(key: string, label = ""): LucideIcon {
  const type = reportType(key);
  return type ? HAZARD_ICONS[type] : HAZARD_KINDS[factorKind(key, label)].icon;
}

export function factorKind(key: string, label = ""): HazardKind {
  if (key in FACTOR_KINDS) return FACTOR_KINDS[key];
  const type = reportType(key);
  if (type) return REPORT_KINDS[type] ?? "crew_report";
  if (key === "alert_nws") return nwsKind(label);
  if (key.startsWith("alert_")) {
    const type = key.slice("alert_".length) as Alert["type"];
    return ALERT_TYPE_KINDS[type] ?? "other";
  }
  return "other";
}

export function alertKind(alert: Pick<Alert, "type" | "meta" | "title">): HazardKind {
  if (alert.type !== "nws") return ALERT_TYPE_KINDS[alert.type];
  const event = (alert.meta as { nws_event?: string }).nws_event ?? alert.title;
  return nwsKind(event);
}

/** A small tinted square with the kind's icon, for lists of factors and alerts. */
export function kindChipStyle(kind: HazardKind): { background: string; color: string } {
  const { color } = HAZARD_KINDS[kind];
  return { background: `${color}26`, color };
}
