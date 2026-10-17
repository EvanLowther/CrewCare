"""Owner: Person A. Real-time weather from the NWS API -> `nws_weather` (migration 005), every 30 minutes.

Free, no key and no daily cap (NWS asks for a User-Agent and reasonable rates), so it carries the Real-time score's
weather while Open-Meteo is polled less often for soil moisture, CAPE and the ML model's inputs. Per site:

- link_sites(): once, /points/{lat},{lon} -> forecast grid, nearest station, forecast zone and county zone.
- poll(): the gridpoint forecast (/gridpoints/{wfo}/{x},{y}) for the hours after now, and the station's latest
  observation (/stations/{id}/observations/latest) as the current hour.

Gridpoint layers are ISO 8601 intervals ("2026-10-17T12:00:00+00:00/PT6H") in SI units. Readings (temperature,
wind, visibility, probabilities) hold for every hour of their interval; amounts (rain, snow, ice) are split evenly
over it.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime, timedelta

import httpx

from planit.config import settings
from planit.db import connection

log = logging.getLogger(__name__)

API = "https://api.weather.gov"
MAX_FORECAST_HOURS = 72
RETRIES = 2
RETRY_WAIT_S = 2

COLUMNS = ["site_id", "ts", "is_forecast", "temp_f", "heat_index_f", "wind_chill_f", "wbgt_f", "humidity_pct",
           "precip_in", "precip_prob_pct", "snowfall_in", "ice_in", "wind_mph", "gust_mph", "visibility_m",
           "thunder_prob_pct", "weather_code"]

# gridpoint layer -> (column, unit, kind). "amount" layers are totals for the interval, the rest hold for each hour.
GRID_LAYERS = {
    "temperature": ("temp_f", "degC", "reading"),
    "heatIndex": ("heat_index_f", "degC", "reading"),
    "windChill": ("wind_chill_f", "degC", "reading"),
    "wetBulbGlobeTemperature": ("wbgt_f", "degC", "reading"),
    "relativeHumidity": ("humidity_pct", "percent", "reading"),
    "probabilityOfPrecipitation": ("precip_prob_pct", "percent", "reading"),
    "probabilityOfThunder": ("thunder_prob_pct", "percent", "reading"),
    "windSpeed": ("wind_mph", "km_h-1", "reading"),
    "windGust": ("gust_mph", "km_h-1", "reading"),
    "visibility": ("visibility_m", "m", "reading"),
    "quantitativePrecipitation": ("precip_in", "mm", "amount"),
    "snowfallAmount": ("snowfall_in", "mm", "amount"),
    "iceAccumulation": ("ice_in", "mm", "amount"),
}

# observation field -> (column, unit)
OBSERVATION_FIELDS = {
    "temperature": ("temp_f", "degC"),
    "heatIndex": ("heat_index_f", "degC"),
    "windChill": ("wind_chill_f", "degC"),
    "relativeHumidity": ("humidity_pct", "percent"),
    "windSpeed": ("wind_mph", "km_h-1"),
    "windGust": ("gust_mph", "km_h-1"),
    "visibility": ("visibility_m", "m"),
    "precipitationLastHour": ("precip_in", "mm"),
}

# NWS forecast "weather" coverage words that mean it's expected, not just possible.
LIKELY_COVERAGE = {"likely", "definite", "numerous", "widespread", "occasional", "frequent", "areas", "patchy"}
THUNDERSTORM_CODE = 95  # WMO: what hazards.thunderstorm() reads
FOG_CODE = 45


def convert(value: float | None, unit: str) -> float | None:
    """SI value -> the unit `nws_weather` stores (°F, mph, inches; percent and meters unchanged)."""
    if value is None:
        return None
    if unit == "degC":
        return round(value * 9 / 5 + 32, 1)
    if unit == "km_h-1":
        return round(value / 1.609344, 1)
    if unit == "mm":
        return round(value / 25.4, 3)
    return round(value, 1)


_DURATION = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$")


def parse_interval(valid_time: str) -> tuple[datetime, int]:
    """'2026-10-17T12:00:00+00:00/P1DT6H' -> (start in UTC, 30 hours). Durations under an hour count as one."""
    start, duration = valid_time.split("/")
    match = _DURATION.match(duration)
    if not match:
        raise ValueError(f"Unknown NWS duration {duration!r}")
    days, hours, minutes = (int(g or 0) for g in match.groups())
    return datetime.fromisoformat(start).astimezone(UTC), max(1, days * 24 + hours + (1 if minutes else 0))


def _unit(layer: dict) -> str:
    return (layer.get("uom") or "").removeprefix("wmoUnit:")


def expand(layer: dict, kind: str) -> dict[datetime, float]:
    """One gridpoint layer -> {hour: value}. Readings repeat over their interval; amounts are split evenly."""
    out: dict[datetime, float] = {}
    for item in layer.get("values", []):
        if item["value"] is None:
            continue
        start, hours = parse_interval(item["validTime"])
        value = item["value"] / hours if kind == "amount" else item["value"]
        for h in range(hours):
            out[start + timedelta(hours=h)] = value
    return out


def weather_codes(layer: dict) -> dict[datetime, int]:
    """The forecast 'weather' layer -> WMO code per hour where thunderstorms (95) or fog (45) are expected."""
    out: dict[datetime, int] = {}
    for item in layer.get("values", []):
        kinds = {w.get("weather") for w in item["value"] or [] if w.get("coverage") in LIKELY_COVERAGE}
        code = THUNDERSTORM_CODE if "thunderstorms" in kinds else FOG_CODE if "fog" in kinds else None
        if code is None:
            continue
        start, hours = parse_interval(item["validTime"])
        for h in range(hours):
            out[start + timedelta(hours=h)] = code
    return out


def forecast_rows(site_id: int, grid: dict, now: datetime) -> list[tuple]:
    """Gridpoint `properties` -> nws_weather rows for the hours after now (up to MAX_FORECAST_HOURS)."""
    first = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    hours = [first + timedelta(hours=h) for h in range(MAX_FORECAST_HOURS)]
    layers = {}
    for name, (col, unit, kind) in GRID_LAYERS.items():
        layer = grid.get(name) or {}
        if _unit(layer) not in ("", unit):
            raise ValueError(f"NWS layer {name} is in {_unit(layer)}, expected {unit}")
        layers[col] = (expand(layer, kind), unit)
    codes = weather_codes(grid.get("weather") or {})
    rows = []
    for hour in hours:
        row = {"site_id": site_id, "ts": hour, "is_forecast": True, "weather_code": codes.get(hour)}
        for col, (values, unit) in layers.items():
            row[col] = convert(values.get(hour), unit)
        if row["temp_f"] is None:  # past the end of the forecast
            continue
        rows.append(tuple(row.get(c) for c in COLUMNS))
    return rows


def observation_row(site_id: int, obs: dict) -> tuple | None:
    """Latest-observation `properties` -> one observed row for the hour it was taken in, or None if it's empty."""
    if not obs.get("timestamp"):
        return None
    ts = datetime.fromisoformat(obs["timestamp"]).astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    row = {"site_id": site_id, "ts": ts, "is_forecast": False}
    for field, (col, unit) in OBSERVATION_FIELDS.items():
        value = (obs.get(field) or {}).get("value")
        row[col] = convert(value, unit)
    weather = {w.get("weather") for w in obs.get("presentWeather") or []}
    row["weather_code"] = THUNDERSTORM_CODE if "thunderstorms" in weather else FOG_CODE if "fog" in weather else None
    if row["temp_f"] is None:
        return None
    return tuple(row.get(c) for c in COLUMNS)


def _zone_id(url: str | None) -> str | None:
    return url.rstrip("/").rsplit("/", 1)[-1] if url else None


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": settings.nws_user_agent, "Accept": "application/geo+json"},
                        timeout=30, follow_redirects=True)


def _get(client: httpx.Client, url: str) -> dict:
    """GET with retries: the gridpoint endpoint returns the odd 500 while a forecast is being rebuilt."""
    for attempt in range(RETRIES + 1):
        resp = client.get(url)
        if resp.status_code < 500 or attempt == RETRIES:
            resp.raise_for_status()
            return resp.json()
        time.sleep(RETRY_WAIT_S * (attempt + 1))
    raise AssertionError("unreachable")


LINK_SQL = """
UPDATE sites SET nws_grid_id = %(grid_id)s, nws_grid_x = %(x)s, nws_grid_y = %(y)s, nws_station = %(station)s,
                 nws_zone = %(zone)s, nws_county_zone = %(county)s
WHERE id = %(id)s
"""


def link_sites() -> int:
    """Look up the forecast grid, nearest station and alert zones for sites that don't have them. Returns how many."""
    with connection() as conn:
        sites = conn.execute("SELECT id, latitude, longitude FROM sites WHERE nws_grid_id IS NULL ORDER BY id"
                             ).fetchall()
    linked = []
    with _client() as client:
        for s in sites:
            try:
                p = _get(client, f"{API}/points/{s['latitude']:.4f},{s['longitude']:.4f}")["properties"]
                stations = _get(client, p["observationStations"] + "?limit=1")["features"]
            except (httpx.HTTPError, KeyError) as exc:
                log.warning("NWS points lookup failed for site %s: %s", s["id"], exc)
                continue
            linked.append({"id": s["id"], "grid_id": p["gridId"], "x": p["gridX"], "y": p["gridY"],
                           "station": stations[0]["properties"]["stationIdentifier"] if stations else None,
                           "zone": _zone_id(p.get("forecastZone")), "county": _zone_id(p.get("county"))})
    if linked:
        with connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.executemany(LINK_SQL, linked)
    log.info("nws link: %d of %d unlinked sites linked", len(linked), len(sites))
    return len(linked)


def upsert(rows: list[tuple]) -> int:
    if not rows:
        return 0
    cols = ", ".join(COLUMNS)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS[3:])
    placeholders = ", ".join(["%s"] * len(COLUMNS))
    with connection() as conn, conn.transaction(), conn.cursor() as cur:
        cur.executemany(f"INSERT INTO nws_weather ({cols}) VALUES ({placeholders}) "
                        f"ON CONFLICT (site_id, ts, is_forecast) DO UPDATE SET {updates}, updated_at = now()", rows)
    return len(rows)


def poll() -> int:
    """Forecast + latest observation for every linked site (linking new sites first). Returns rows written."""
    link_sites()
    with connection() as conn:
        sites = conn.execute("SELECT id, nws_grid_id, nws_grid_x, nws_grid_y, nws_station FROM sites "
                             "WHERE nws_grid_id IS NOT NULL ORDER BY id").fetchall()
    now = datetime.now(UTC)
    total, failed = 0, 0
    with _client() as client:
        for s in sites:
            rows = []
            try:
                grid = _get(client, f"{API}/gridpoints/{s['nws_grid_id']}/{s['nws_grid_x']},{s['nws_grid_y']}")
                rows += forecast_rows(s["id"], grid["properties"], now)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                failed += 1
                log.warning("NWS forecast failed for site %s: %s", s["id"], exc)
            if s["nws_station"]:  # some stations stop reporting; the forecast still counts without them
                try:
                    obs = _get(client, f"{API}/stations/{s['nws_station']}/observations/latest")
                    if (row := observation_row(s["id"], obs["properties"])) is not None:
                        rows.append(row)
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    log.info("NWS observation unavailable for site %s (%s): %s", s["id"], s["nws_station"], exc)
            total += upsert(rows)
    log.info("nws weather: %d rows for %d sites (%d failed)", total, len(sites) - failed, failed)
    return total
