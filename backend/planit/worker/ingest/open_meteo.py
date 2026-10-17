"""Owner: Person A. Hourly weather for every site -> `weather` table (Open-Meteo, no key).

- backfill_history(): years of observed weather for ML training (archive API).
- poll(): last 24 h + 3-day forecast (forecast API), every 30 minutes from the worker.

Free-tier budget: 10,000 "calls" a day, where one location x two weeks of data counts as one
call. The 3-year backfill for 60 sites costs ~4,700; a 60-site poll costs 60, so poll every
30 minutes, not every few.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime

import httpx

from planit.db import connection

log = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

UNITS = {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch",
         "timezone": "GMT"}

# Open-Meteo variable -> `weather` column. The archive has no CAPE or precipitation probability,
# so those stay null in history; thunderstorms there show up as weather_code 95-99.
ARCHIVE_VARS = {
    "temperature_2m": "temp_f",
    "apparent_temperature": "heat_index_f",
    "relative_humidity_2m": "humidity_pct",
    "precipitation": "precip_in",
    "wind_speed_10m": "wind_mph",
    "wind_gusts_10m": "gust_mph",
    "weather_code": "weather_code",
    "soil_moisture_0_to_7cm": "soil_moisture",
}

WEATHER_COLUMNS = ["site_id", "ts", "is_forecast", "temp_f", "heat_index_f", "humidity_pct", "precip_in",
                   "precip_prob_pct", "wind_mph", "gust_mph", "cape_jkg", "soil_moisture", "weather_code"]

# The forecast API has CAPE and rain probability, and soil in 0-1 / 1-3 / 3-9 cm layers instead of the
# archive's 0-7 cm; blend_soil_moisture() combines them so live and historical values are comparable.
FORECAST_VARS = {
    **{k: v for k, v in ARCHIVE_VARS.items() if k != "soil_moisture_0_to_7cm"},
    "precipitation_probability": "precip_prob_pct",
    "cape": "cape_jkg",
}
FORECAST_SOIL_LAYERS = {"soil_moisture_0_to_1cm": 1, "soil_moisture_1_to_3cm": 2, "soil_moisture_3_to_9cm": 4}

SITES_PER_REQUEST = 5  # keeps each archive request well under the per-minute budget
FORECAST_SITES_PER_REQUEST = 20
MAX_RETRIES = 6


def chunks(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def year_ranges(start: date, end: date) -> Iterator[tuple[date, date]]:
    """Split [start, end] into calendar-year pieces so each request stays a manageable size."""
    year = start.year
    while year <= end.year:
        yield max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
        year += 1


def hourly_rows(site_id: int, hourly: dict, variables: dict[str, str], now: datetime | None = None,
                ) -> list[tuple]:
    """Turn one location's Open-Meteo `hourly` block into `weather` rows.

    With `now`, hours after it are marked as forecast; without it every hour is observed.
    """
    rows = []
    for i, stamp in enumerate(hourly["time"]):
        ts = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
        values = {col: hourly[var][i] for var, col in variables.items() if var in hourly}
        if all(v is None for v in values.values()):
            continue
        is_forecast = now is not None and ts > now
        row = {"site_id": site_id, "ts": ts, "is_forecast": is_forecast, **values}
        rows.append(tuple(row.get(c) for c in WEATHER_COLUMNS))
    return rows


def fetch(client: httpx.Client, url: str, params: dict) -> list[dict]:
    """GET with backoff on rate limits and server errors. Always returns a list of locations."""
    for attempt in range(MAX_RETRIES):
        resp = client.get(url, params=params, timeout=120)
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = 60 if resp.status_code == 429 else 10 * (attempt + 1)
            log.warning("Open-Meteo %s (%s); retrying in %ss", resp.status_code, resp.text[:120], wait)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else [data]
    raise RuntimeError(f"Open-Meteo kept failing after {MAX_RETRIES} attempts")


def upsert_weather(rows: Iterable[tuple]) -> int:
    """Bulk upsert: COPY into a temp table, then one INSERT ... ON CONFLICT. Returns rows written."""
    cols = ", ".join(WEATHER_COLUMNS)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in WEATHER_COLUMNS[3:])
    with connection() as conn, conn.transaction():
        conn.execute("CREATE TEMP TABLE weather_in (LIKE weather INCLUDING DEFAULTS) ON COMMIT DROP")
        with conn.cursor().copy(f"COPY weather_in ({cols}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
        result = conn.execute(
            f"INSERT INTO weather ({cols}) SELECT {cols} FROM weather_in "
            f"ON CONFLICT (site_id, ts, is_forecast) DO UPDATE SET {updates}, updated_at = now()"
        )
        return result.rowcount


def load_sites() -> list[dict]:
    with connection() as conn:
        return conn.execute("SELECT id, latitude, longitude FROM sites ORDER BY id").fetchall()


def backfill_history(start: str, end: str) -> int:
    """Observed hourly weather for every site between two ISO dates, for ML training."""
    sites = load_sites()
    total = 0
    with httpx.Client() as client:
        for first, last in year_ranges(date.fromisoformat(start), date.fromisoformat(end)):
            for batch in chunks(sites, SITES_PER_REQUEST):
                params = {
                    "latitude": ",".join(str(s["latitude"]) for s in batch),
                    "longitude": ",".join(str(s["longitude"]) for s in batch),
                    "start_date": first.isoformat(),
                    "end_date": last.isoformat(),
                    "hourly": ",".join(ARCHIVE_VARS),
                    **UNITS,
                }
                locations = fetch(client, ARCHIVE_URL, params)
                rows = [r for site, loc in zip(batch, locations, strict=True)
                        for r in hourly_rows(site["id"], loc["hourly"], ARCHIVE_VARS)]
                total += upsert_weather(rows)
                log.info("history %s..%s sites %s: %d rows (total %d)", first, last,
                         [s["id"] for s in batch], len(rows), total)
                time.sleep(15)  # stay under the per-minute budget
    return total


def refresh_daily_rollup(start: str, end: str) -> None:
    """The weather_daily policy only refreshes the last few days, so refresh history explicitly."""
    with connection() as conn:
        conn.autocommit = True  # CALL refresh_continuous_aggregate can't run inside a transaction
        try:
            conn.execute("CALL refresh_continuous_aggregate('weather_daily', %s::timestamptz, %s::timestamptz)",
                         (start, end))
        finally:
            conn.autocommit = False


def blend_soil_moisture(hourly: dict) -> dict:
    """Add a 0-7 cm soil moisture series to a forecast `hourly` block, weighting layers by depth used."""
    layers = [(hourly.get(name), weight) for name, weight in FORECAST_SOIL_LAYERS.items()]
    blended = []
    for i in range(len(hourly["time"])):
        values = [(series[i], w) for series, w in layers if series is not None and series[i] is not None]
        blended.append(round(sum(v * w for v, w in values) / sum(w for _, w in values), 4) if values else None)
    return {**hourly, "soil_moisture_0_to_7cm": blended}


def poll() -> int:
    """Last 24 h of observations + 3-day forecast for every site. Hours after now are stored as forecast."""
    sites = load_sites()
    now = datetime.now(UTC)
    variables = {**FORECAST_VARS, "soil_moisture_0_to_7cm": "soil_moisture"}
    total = 0
    with httpx.Client() as client:
        for batch in chunks(sites, FORECAST_SITES_PER_REQUEST):
            params = {
                "latitude": ",".join(str(s["latitude"]) for s in batch),
                "longitude": ",".join(str(s["longitude"]) for s in batch),
                "past_days": 1,
                "forecast_days": 3,
                "hourly": ",".join([*FORECAST_VARS, *FORECAST_SOIL_LAYERS]),
                **UNITS,
            }
            locations = fetch(client, FORECAST_URL, params)
            rows = [r for site, loc in zip(batch, locations, strict=True)
                    for r in hourly_rows(site["id"], blend_soil_moisture(loc["hourly"]), variables, now=now)]
            total += upsert_weather(rows)
    log.info("open-meteo poll: %d rows for %d sites", total, len(sites))
    return total
