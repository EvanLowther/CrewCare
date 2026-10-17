/** Small display helpers shared across pages. */

export function relativeTime(iso: string, now: number = Date.now()): string {
  const diffMin = Math.round((now - new Date(iso).getTime()) / 60_000);
  if (diffMin < 0) {
    const ahead = -diffMin;
    if (ahead < 60) return `in ${ahead} min`;
    if (ahead < 48 * 60) return `in ${Math.round(ahead / 60)} h`;
    return `in ${Math.round(ahead / 1440)} d`;
  }
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin} min ago`;
  if (diffMin < 48 * 60) return `${Math.round(diffMin / 60)} h ago`;
  return `${Math.round(diffMin / 1440)} d ago`;
}

/** Time of day in the site's own timezone, e.g. "2:40 PM". */
export function siteTime(iso: string, timeZone: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone });
}

export function siteHour(iso: string, timeZone: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", timeZone });
}

export function siteDay(iso: string, timeZone: string): string {
  return new Date(iso).toLocaleDateString("en-US", { weekday: "short", timeZone });
}

export function round(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined ? "–" : value.toFixed(digits);
}

export function titleCase(text: string): string {
  return text.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}
