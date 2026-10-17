"""Owner: Person A. Training rows for the hazard model: one row per (site, day).

Features come from `weather_daily`, plus the day's heaviest hour of rain from `weather` as the storm signal: the
Open-Meteo archive has no CAPE and never reports thunderstorm weather codes (95-99).

Label = 1 if a crew-relevant NOAA storm event happened that day within LABEL_RADIUS_MI of the site, or anywhere in
its county (zone-wide events such as heat and tropical storms have no coordinates). Days are UTC, like
`weather_daily`. Live scoring must build its rows with add_features() so the model sees the same columns.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from planit.db import connection

FEATURES = [
    "max_heat_index_f",
    "total_precip_in",
    "precip_prev_3d_in",
    "avg_soil_moisture",
    "max_gust_mph",
    "max_hourly_precip_in",
    "month",
]

# Weather that threatens field crews and that the features can see coming. Left out: Drought, Rip Current,
# Coastal Flood, Wildfire, cold and snow.
HAZARD_EVENT_TYPES = {
    "Thunderstorm Wind", "Lightning", "Hail", "Tornado", "Funnel Cloud", "Heavy Rain", "Flash Flood", "Flood",
    "Excessive Heat", "Heat", "Tropical Storm", "Tropical Depression", "Hurricane (Typhoon)", "Storm Surge/Tide",
    "Strong Wind", "High Wind",
}
LABEL_RADIUS_MI = 25.0
MAX_EVENT_DAYS = 3  # a multi-day event (tropical storm, heat wave) labels at most its first 3 days
EARTH_RADIUS_MI = 3958.8

DAILY_SQL = """
SELECT d.site_id, d.day, d.max_heat_index_f, d.total_precip_in, d.avg_soil_moisture, d.max_gust_mph,
       h.max_hourly_precip_in
FROM weather_daily d
LEFT JOIN (
    SELECT site_id, time_bucket('1 day', ts) AS day, max(precip_in) AS max_hourly_precip_in
    FROM weather
    WHERE NOT is_forecast AND ts >= %(start)s AND ts < %(end)s
    GROUP BY 1, 2
) h USING (site_id, day)
WHERE d.day >= %(start)s AND d.day < %(end)s
"""


def utc_day(values: pd.Series) -> pd.Series:
    """Timestamps -> naive midnight-UTC days, so days from Postgres and from NOAA compare equal."""
    return pd.to_datetime(values, utc=True).dt.tz_localize(None).dt.normalize()


def normalize_county(name: object) -> str:
    """'MIAMI-DADE' and 'Miami Dade' -> 'MIAMI DADE'; 'ST. JOHNS' -> 'ST JOHNS'."""
    if not isinstance(name, str):
        return ""
    return " ".join(re.sub(r"[^A-Z ]", " ", name.upper()).split())


def miles(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Haversine distance; NaN where either point is missing."""
    lat1, lon1, lat2, lon2 = (pd.to_numeric(pd.Series(v), errors="coerce").to_numpy(float)
                              for v in (lat1, lon1, lat2, lon2))
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(a))


def add_features(daily: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns to daily rows (site_id, day, max_heat_index_f, total_precip_in, avg_soil_moisture,
    max_gust_mph, max_hourly_precip_in). Assumes one row per site per day, without gaps."""
    out = daily.assign(day=utc_day(daily["day"])).sort_values(["site_id", "day"]).reset_index(drop=True)
    out["precip_prev_3d_in"] = out.groupby("site_id")["total_precip_in"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).sum())
    out["month"] = out["day"].dt.month
    return out


def label_days(sites: pd.DataFrame, events: pd.DataFrame, radius_mi: float = LABEL_RADIUS_MI) -> pd.DataFrame:
    """(site_id, day, label=1) for every site-day with a hazardous event nearby or in the site's county.

    sites: id, county, latitude, longitude. events: event_type, begin_ts, end_ts, cz_name, latitude, longitude.
    """
    ev = events[events["event_type"].isin(HAZARD_EVENT_TYPES)].copy()
    if ev.empty:
        return pd.DataFrame({"site_id": pd.Series(dtype=int), "day": pd.Series(dtype="datetime64[ns]"),
                             "label": pd.Series(dtype=int)})
    first = utc_day(ev["begin_ts"])
    last = utc_day(ev["end_ts"].fillna(ev["begin_ts"]))
    last = last.clip(lower=first, upper=first + pd.Timedelta(days=MAX_EVENT_DAYS - 1))
    ev["day"] = [list(pd.date_range(f, t, freq="D")) for f, t in zip(first, last, strict=True)]
    ev = ev.explode("day")
    ev["cz"] = ev["cz_name"].map(normalize_county)

    site_cols = sites.rename(columns={"id": "site_id", "latitude": "site_lat", "longitude": "site_lon"})
    site_cols = site_cols.assign(site_county=site_cols["county"].map(normalize_county))
    pairs = site_cols[["site_id", "site_county", "site_lat", "site_lon"]].merge(
        ev[["day", "cz", "latitude", "longitude"]], how="cross")
    near = miles(pairs["site_lat"], pairs["site_lon"], pairs["latitude"], pairs["longitude"]) <= radius_mi
    same_county = pairs["site_county"] == pairs["cz"]
    hits = pairs.loc[near | same_county, ["site_id", "day"]].drop_duplicates()
    hits["day"] = pd.to_datetime(hits["day"])
    return hits.assign(label=1).reset_index(drop=True)


def training_frame(start: str = "2023-01-01", end: str = "2026-01-01") -> pd.DataFrame:
    """Features + label for every site-day in [start, end). Storm Events are loaded for 2023-2025."""
    window = {"start": start, "end": end}
    with connection() as conn:
        daily = pd.DataFrame(conn.execute(DAILY_SQL, window).fetchall())
        sites = pd.DataFrame(conn.execute("SELECT id, county, latitude, longitude FROM sites").fetchall())
        events = pd.DataFrame(conn.execute(
            "SELECT event_type, begin_ts, end_ts, cz_name, latitude, longitude FROM storm_events "
            "WHERE begin_ts >= %(start)s AND begin_ts < %(end)s", window).fetchall())
    frame = add_features(daily).merge(label_days(sites, events), on=["site_id", "day"], how="left")
    frame["label"] = frame["label"].fillna(0).astype(int)
    return frame
