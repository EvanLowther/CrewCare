"""Owner: Person A. Training rows for the hazard model: one row per (site, day).

Features come from `weather_daily`, plus per-day extremes from hourly `weather`: the heaviest hour of rain as the
storm signal (the Open-Meteo archive has no CAPE and never reports thunderstorm weather codes 95-99), and the
coldest temperature and wind chill, snowfall, snow depth and driest hour for the cold, winter and fire-weather
hazards outside Florida. The site's latitude and longitude let one national model learn what's normal where.

Label = 1 if a crew-relevant NOAA storm event happened that day within LABEL_RADIUS_MI of the site, or anywhere in
its county (zone-wide events such as heat, snow and tropical storms have no coordinates) in the same state. Days
are UTC, like `weather_daily`. Live scoring builds the same columns in score.window_features().
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from planit.db import connection
from planit.states import STATE_CODES

FEATURES = [
    "max_heat_index_f",
    "total_precip_in",
    "precip_prev_3d_in",
    "avg_soil_moisture",
    "max_gust_mph",
    "max_hourly_precip_in",
    "month",
    "min_temp_f",
    "min_wind_chill_f",
    "total_snowfall_in",
    "max_snow_depth_ft",
    "min_humidity_pct",
    "latitude",
    "longitude",
]

# Weather that threatens field crews and that the features can see coming. Left out: Drought, Rip Current and
# Frost/Freeze (not a crew hazard on the day), Dense Fog (no visibility feature), Coastal Flood and Debris Flow
# (no tide or slope data): rules-v2 and NWS alerts cover those.
HAZARD_EVENT_TYPES = {
    "Thunderstorm Wind", "Lightning", "Hail", "Tornado", "Funnel Cloud", "Heavy Rain", "Flash Flood", "Flood",
    "Excessive Heat", "Heat", "Tropical Storm", "Tropical Depression", "Hurricane (Typhoon)", "Storm Surge/Tide",
    "Strong Wind", "High Wind",
    # National: cold, winter and fire weather
    "Extreme Cold/Wind Chill", "Cold/Wind Chill", "Winter Storm", "Winter Weather", "Heavy Snow", "Blizzard",
    "Ice Storm", "Lake-Effect Snow", "Sleet", "Wildfire", "Dust Storm",
}
LABEL_RADIUS_MI = 25.0
MAX_EVENT_DAYS = 3  # a multi-day event (tropical storm, heat wave) labels at most its first 3 days
EARTH_RADIUS_MI = 3958.8
# Weather history from before migration 004 has no snow columns (Florida's 2023-2025 backfill). Snow can't fall or
# lie on a day that never drops below this, so those days count as no snow instead of unknown.
NO_SNOW_ABOVE_F = 34.0

# Wind chill matches hazards.wind_chill_f().
DAILY_SQL = """
SELECT d.site_id, d.day, d.max_heat_index_f, d.total_precip_in, d.avg_soil_moisture, d.max_gust_mph,
       h.max_hourly_precip_in, h.min_temp_f, h.min_wind_chill_f, h.total_snowfall_in, h.max_snow_depth_ft,
       h.min_humidity_pct, s.latitude, s.longitude
FROM weather_daily d
JOIN sites s ON s.id = d.site_id
LEFT JOIN (
    SELECT site_id, time_bucket('1 day', ts) AS day, max(precip_in) AS max_hourly_precip_in,
           min(temp_f) AS min_temp_f,
           min(CASE WHEN temp_f <= 50 AND wind_mph >= 3
                    THEN 35.74 + 0.6215 * temp_f - 35.75 * power(wind_mph, 0.16)
                         + 0.4275 * temp_f * power(wind_mph, 0.16)
                    ELSE temp_f END) AS min_wind_chill_f,
           sum(snowfall_in) AS total_snowfall_in, max(snow_depth_ft) AS max_snow_depth_ft,
           min(humidity_pct) AS min_humidity_pct
    FROM weather
    WHERE NOT is_forecast AND ts >= %(start)s AND ts < %(end)s
    GROUP BY 1, 2
) h USING (site_id, day)
WHERE d.day >= %(start)s AND d.day < %(end)s
"""


def utc_day(values: pd.Series) -> pd.Series:
    """Timestamps -> naive midnight-UTC days, so days from Postgres and from NOAA compare equal."""
    return pd.to_datetime(values, utc=True).dt.tz_localize(None).dt.normalize()


# NWS forecast zones wrap the county name: 'COASTAL HILLSBOROUGH', 'INLAND PALM BEACH COUNTY', 'METRO BROWARD',
# 'MONROE/LOWER KEYS', 'SOUTHERN BREVARD BARRIER ISLANDS', 'FAR SOUTH MIAMI-DADE COUNTY'.
ZONE_WORDS = {"COASTAL", "INLAND", "METRO", "METROPOLITAN", "MAINLAND", "COUNTY", "FAR", "NORTH", "SOUTH", "EAST",
              "WEST", "CENTRAL", "NORTHERN", "SOUTHERN", "EASTERN", "WESTERN", "NORTHEAST", "NORTHWEST", "SOUTHEAST",
              "SOUTHWEST", "UPPER", "MIDDLE", "LOWER", "KEYS", "BARRIER", "ISLANDS"}


def normalize_county(name: object) -> str:
    """County or zone name -> comparable key: 'COASTAL MIAMI-DADE COUNTY' and 'Miami Dade' -> 'MIAMIDADE',
    'ST. JOHNS' -> 'STJOHNS', 'DE SOTO' and 'DeSoto' -> 'DESOTO'."""
    if not isinstance(name, str):
        return ""
    words = re.sub(r"[^A-Z ]", " ", name.upper()).split()
    return "".join(w for w in words if w not in ZONE_WORDS)


def miles(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Haversine distance; NaN where either point is missing."""
    lat1, lon1, lat2, lon2 = (pd.to_numeric(pd.Series(v), errors="coerce").to_numpy(float)
                              for v in (lat1, lon1, lat2, lon2))
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(a))


def add_features(daily: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns to daily rows (site_id, day and the DAILY_SQL columns). Assumes one row per site per day,
    without gaps."""
    out = daily.assign(day=utc_day(daily["day"])).sort_values(["site_id", "day"]).reset_index(drop=True)
    out["precip_prev_3d_in"] = out.groupby("site_id")["total_precip_in"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).sum())
    out["month"] = out["day"].dt.month
    for col in ("total_snowfall_in", "max_snow_depth_ft"):
        if col in out and "min_temp_f" in out:
            warm = pd.to_numeric(out["min_temp_f"], errors="coerce") > NO_SNOW_ABOVE_F
            out[col] = pd.to_numeric(out[col], errors="coerce").mask(warm & out[col].isna(), 0.0)
    return out


def state_county(state: object, county: object) -> str:
    """'FL' or 'FLORIDA' + 'Miami Dade' -> 'FL:MIAMIDADE', so Washington County, OR never matches Washington
    County, AL."""
    code = STATE_CODES.get(state, state) if isinstance(state, str) else ""
    return f"{code}:{normalize_county(county)}"


def label_days(sites: pd.DataFrame, events: pd.DataFrame, radius_mi: float = LABEL_RADIUS_MI) -> pd.DataFrame:
    """(site_id, day, label=1) for every site-day with a hazardous event nearby or in the site's county.

    sites: id, state, county, latitude, longitude. events: event_type, begin_ts, end_ts, state, cz_name, latitude,
    longitude. States are postal codes for sites and NOAA names ('FLORIDA') or codes for events.
    """
    empty = pd.DataFrame({"site_id": pd.Series(dtype=int), "day": pd.Series(dtype="datetime64[ns]"),
                          "label": pd.Series(dtype=int)})
    ev = events[events["event_type"].isin(HAZARD_EVENT_TYPES)].copy()
    if ev.empty:
        return empty
    first = utc_day(ev["begin_ts"])
    last = utc_day(ev["end_ts"].fillna(ev["begin_ts"]))
    last = last.clip(lower=first, upper=first + pd.Timedelta(days=MAX_EVENT_DAYS - 1))
    ev["day"] = [list(pd.date_range(f, t, freq="D")) for f, t in zip(first, last, strict=True)]
    ev = ev.explode("day")
    zones = np.array([state_county(s, c) for s, c in zip(ev["state"], ev["cz_name"], strict=True)])
    days, ev_lat, ev_lon = ev["day"].to_numpy(), ev["latitude"].to_numpy(), ev["longitude"].to_numpy()

    # One site at a time against every event: a site x event cross join is 100M+ rows nationally.
    hits = []
    for site in sites.itertuples(index=False):
        near = miles(np.full(len(ev), site.latitude), np.full(len(ev), site.longitude), ev_lat, ev_lon) <= radius_mi
        mask = near | (zones == state_county(site.state, site.county))
        if mask.any():
            hits.append(pd.DataFrame({"site_id": site.id, "day": days[mask]}))
    if not hits:
        return empty
    out = pd.concat(hits).drop_duplicates()
    out["day"] = pd.to_datetime(out["day"])
    return out.assign(label=1).reset_index(drop=True)


def load_inputs(start: str = "2023-01-01", end: str = "2026-01-01") -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(daily weather, sites, storm events) for [start, end). Storm Events: Florida 2023-2025, every state 2024-2025,
    matching the weather history (Florida's sites from 2023, the rest from 2024)."""
    window = {"start": start, "end": end}
    with connection() as conn:
        daily = pd.DataFrame(conn.execute(DAILY_SQL, window).fetchall())
        sites = pd.DataFrame(conn.execute("SELECT id, state, county, latitude, longitude FROM sites").fetchall())
        events = pd.DataFrame(conn.execute(
            "SELECT event_type, begin_ts, end_ts, state, cz_name, latitude, longitude FROM storm_events "
            "WHERE begin_ts >= %(start)s AND begin_ts < %(end)s", window).fetchall())
    return daily, sites, events


def build_frame(daily: pd.DataFrame, sites: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    frame = add_features(daily).merge(label_days(sites, events), on=["site_id", "day"], how="left")
    frame["label"] = frame["label"].fillna(0).astype(int)
    return frame


def training_frame(start: str = "2023-01-01", end: str = "2026-01-01") -> pd.DataFrame:
    """Features + label for every site-day in [start, end)."""
    return build_frame(*load_inputs(start, end))
