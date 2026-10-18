"""Owner: Person A. Hourly air quality for every site -> `air_quality` table (Open-Meteo Air Quality API, no key).

API: https://air-quality-api.open-meteo.com/v1/air-quality. US AQI (worst pollutant), US AQI for PM2.5 alone and
the PM2.5 concentration, for the last day and the next two, from the CAMS air-quality model. Smoke is what PM2.5
measures; hazards.smoke() scores the PM2.5 AQI on the EPA categories and Cal/OSHA 5141.1. These are modelled values,
not monitor readings (AirNow monitors would need a key).

Runs every 2 h. A 160-site poll with 3 variables over 3 days costs 160 Open-Meteo calls (open_meteo.call_weight()),
~1,900 a day next to open_meteo.poll()'s ~1,800, well under the 10,000 free a day.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from planit.db import connection
from planit.worker.ingest.open_meteo import chunks, fetch, load_sites

log = logging.getLogger(__name__)

AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
VARIABLES = {"us_aqi": "us_aqi", "us_aqi_pm2_5": "us_aqi_pm2_5", "pm2_5": "pm2_5_ugm3"}  # Open-Meteo -> column
COLUMNS = ["site_id", "ts", "is_forecast", *VARIABLES.values()]
SITES_PER_REQUEST = 20


def hourly_rows(site_id: int, hourly: dict, now: datetime) -> list[tuple]:
    """One location's `hourly` block -> `air_quality` rows; hours after `now` are forecast."""
    rows = []
    for i, stamp in enumerate(hourly["time"]):
        values = [hourly[var][i] if var in hourly else None for var in VARIABLES]
        if all(v is None for v in values):
            continue
        ts = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
        rows.append((site_id, ts, ts > now, *values))
    return rows


def upsert(rows: list[tuple]) -> int:
    cols = ", ".join(COLUMNS)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS[3:])
    with connection() as conn, conn.transaction():
        conn.execute("CREATE TEMP TABLE air_quality_in (LIKE air_quality INCLUDING DEFAULTS) ON COMMIT DROP")
        with conn.cursor().copy(f"COPY air_quality_in ({cols}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
        result = conn.execute(
            f"INSERT INTO air_quality ({cols}) SELECT {cols} FROM air_quality_in "
            f"ON CONFLICT (site_id, ts, is_forecast) DO UPDATE SET {updates}, updated_at = now()"
        )
        return result.rowcount


def poll(site_ids: list[int] | None = None) -> int:
    """Last day + 2-day forecast of air quality for every site (or just `site_ids`). Returns rows written."""
    sites = [s for s in load_sites() if site_ids is None or s["id"] in site_ids]
    now = datetime.now(UTC)
    rows = []
    with httpx.Client() as client:
        for batch in chunks(sites, SITES_PER_REQUEST):
            params = {
                "latitude": ",".join(str(s["latitude"]) for s in batch),
                "longitude": ",".join(str(s["longitude"]) for s in batch),
                "hourly": ",".join(VARIABLES),
                "past_days": 1,
                "forecast_days": 2,
                "timezone": "GMT",
            }
            locations = fetch(client, AIR_QUALITY_URL, params)
            rows += [r for site, loc in zip(batch, locations, strict=True)
                     for r in hourly_rows(site["id"], loc["hourly"], now)]
    total = upsert(rows)
    log.info("air quality poll: %d rows for %d sites", total, len(sites))
    return total
