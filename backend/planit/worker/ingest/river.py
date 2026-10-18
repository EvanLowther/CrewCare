"""Owner: Person A. River gauges near sites -> `river_gauges` / `river_levels` (NOAA NWPS, no key).

API: https://api.water.noaa.gov/nwps/v1 (NOAA's National Water Prediction Service). Most of its gauges are USGS gauges;
NWS adds flood stages (action, minor = flood stage, moderate, major) and a river forecast for many of them.

- link_sites(): once per new or moved site, the nearest gauge within MATCH_RADIUS_MI that has NWS flood stages
  becomes the site's gauge (sites.usgs_gauge_id). Gauges without flood stages (creeks, canals) are skipped, since
  "rising toward flood stage" means nothing for them, and so are tide gauges (coastal, not a river). Sites with none
  get river_checked_at and no gauge. Requests are paced (NWPS answers bursts with 429).
- poll() every 15 min: for each matched gauge, the latest observed stage and the highest NWS forecast stage in the
  next FORECAST_HOURS -> river_levels. rules/flood.py turns them into flood-risk warnings.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import UTC, datetime, timedelta

import httpx

from planit import hazards
from planit.db import connection

log = logging.getLogger(__name__)

API = "https://api.water.noaa.gov/nwps/v1"
MATCH_RADIUS_MI = 2.0
FORECAST_HOURS = 48
NO_VALUE = -900.0  # NWPS uses -999 / -9999 for "none"
STAGE_NAMES = ("action", "minor", "moderate", "major")
# SHEF codes of what a gauge measures (pedts.observed): HG river stage, HP reservoir pool at a dam. Tide and coastal
# water-level gauges (HM...) have flood stages too, but they're coastal flooding, not a river.
RIVER_PEDTS = ("HG", "HP")
NOT_A_RIVER = ("tide", "ocean", "atlantic coast", "gulf coast", "pacific coast")
REQUEST_PAUSE_S = 0.4  # NWPS answers 429 to bursts
RETRIES = 3
# Linking more sites than this reads the national gauge list once instead of searching around each site.
FEW_SITES = 5
US_BBOX = {"bbox.xmin": -180.0, "bbox.ymin": 15.0, "bbox.xmax": -60.0, "bbox.ymax": 72.0, "srid": "EPSG_4326"}


def _value(v) -> float | None:
    return None if v is None or float(v) <= NO_VALUE else float(v)


def stages(detail: dict) -> dict:
    """{"action", "minor", "moderate", "major"} -> feet (None where NWS has none) from a /gauges/{lid} reply."""
    categories = (detail.get("flood") or {}).get("categories") or {}
    return {name: _value((categories.get(name) or {}).get("stage")) for name in STAGE_NAMES}


def has_flood_stages(detail: dict) -> bool:
    return stages(detail)["minor"] is not None


def is_river(detail: dict) -> bool:
    """A river (or dam pool) gauge, not a tide or coastal water-level one."""
    code = ((detail.get("pedts") or {}).get("observed") or "").upper()
    name = (detail.get("name") or "").lower()
    return code.startswith(RIVER_PEDTS) and not any(word in name for word in NOT_A_RIVER)


def river_name(gauge_name: str) -> str:
    """'Mississippi River at Baton Rouge' -> 'Mississippi River'."""
    for sep in (" at ", " near ", " above ", " below "):
        if sep in gauge_name:
            return gauge_name.split(sep)[0].strip()
    return gauge_name.strip()


def bbox(lat: float, lon: float, miles: float) -> dict:
    dlat = miles / 69.0
    dlon = miles / (69.0 * max(0.1, math.cos(math.radians(lat))))
    return {"bbox.xmin": lon - dlon, "bbox.ymin": lat - dlat, "bbox.xmax": lon + dlon, "bbox.ymax": lat + dlat,
            "srid": "EPSG_4326"}


def candidates(site: dict, gauges: list[dict], radius_mi: float = MATCH_RADIUS_MI) -> list[tuple[float, dict]]:
    """Gauges within `radius_mi` of the site that are in service, nearest first, as (miles, gauge)."""
    out = []
    for g in gauges:
        if (g.get("status") or {}).get("observed", {}).get("floodCategory") == "out_of_service":
            continue
        if g.get("latitude") is None or g.get("longitude") is None:
            continue
        miles = hazards.miles_between(site["latitude"], site["longitude"], g["latitude"], g["longitude"])
        if miles <= radius_mi:
            out.append((miles, g))
    return sorted(out, key=lambda c: c[0])


def gauge_row(detail: dict) -> dict:
    st = stages(detail)
    return {"gauge_id": detail["lid"], "name": detail.get("name") or detail["lid"],
            "river": river_name(detail.get("name") or ""), "latitude": detail.get("latitude"),
            "longitude": detail.get("longitude"), "action": st["action"], "flood": st["minor"],
            "moderate": st["moderate"], "major": st["major"], "usgs_id": detail.get("usgsId") or None}


UPSERT_GAUGE = """
INSERT INTO river_gauges (gauge_id, name, river, latitude, longitude, action_stage_ft, flood_stage_ft,
                          moderate_stage_ft, major_stage_ft, usgs_id)
VALUES (%(gauge_id)s, %(name)s, %(river)s, %(latitude)s, %(longitude)s, %(action)s, %(flood)s, %(moderate)s,
        %(major)s, %(usgs_id)s)
ON CONFLICT (gauge_id) DO UPDATE SET name = EXCLUDED.name, river = EXCLUDED.river, latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude, action_stage_ft = EXCLUDED.action_stage_ft,
    flood_stage_ft = EXCLUDED.flood_stage_ft, moderate_stage_ft = EXCLUDED.moderate_stage_ft,
    major_stage_ft = EXCLUDED.major_stage_ft, usgs_id = EXCLUDED.usgs_id
"""


def _get(client: httpx.Client, path: str, params: dict | None = None) -> dict:
    """GET with a short pause between requests, and backoff when NWPS rate-limits (429)."""
    for attempt in range(RETRIES + 1):
        time.sleep(REQUEST_PAUSE_S)
        resp = client.get(f"{API}{path}", params=params)
        if resp.status_code == 429 and attempt < RETRIES:
            time.sleep(float(resp.headers.get("Retry-After") or 0) or 10 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("unreachable")


def link_sites(site_ids: list[int] | None = None) -> int:
    """Match sites not checked yet (or just `site_ids`) to their nearest flood-staged gauge. Returns sites matched."""
    with connection() as conn:
        sites = conn.execute(
            "SELECT id, latitude, longitude FROM sites WHERE river_checked_at IS NULL "
            "AND (%(ids)s::int[] IS NULL OR id = ANY(%(ids)s)) ORDER BY id", {"ids": site_ids}).fetchall()
    if not sites:
        return 0
    matched, checked = [], []
    with httpx.Client(timeout=120) as client:
        national = None
        if len(sites) > FEW_SITES:  # one national list beats a search per site (NWPS rate-limits searches)
            try:
                national = _get(client, "/gauges", US_BBOX).get("gauges", [])
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    log.warning("NWPS is rate-limiting; linking sites next poll")
                    return 0
                log.warning("NWPS national gauge list failed (%s); searching around each site", exc)
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("NWPS national gauge list failed: %s", exc)
                return 0  # try again next poll
        for s in sites:
            try:
                listed = national if national is not None else _get(
                    client, "/gauges", bbox(s["latitude"], s["longitude"], MATCH_RADIUS_MI)).get("gauges", [])
                near = [(m, g) for m, g in candidates(s, listed) if is_river(g)]  # list entries carry pedts too
                gauge = None
                for _, g in near:  # the nearest river gauge NWS gives flood stages for
                    detail = _get(client, f"/gauges/{g['lid']}")
                    if has_flood_stages(detail) and is_river(detail):
                        gauge = gauge_row(detail)
                        break
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                log.warning("NWPS gauge lookup failed for site %s: %s", s["id"], exc)
                continue  # try again next poll
            checked.append(s["id"])
            if gauge:
                matched.append((s["id"], gauge))
    with connection() as conn, conn.transaction(), conn.cursor() as cur:
        for site_id, gauge in matched:
            cur.execute(UPSERT_GAUGE, gauge)
            cur.execute("UPDATE sites SET usgs_gauge_id = %s WHERE id = %s", (gauge["gauge_id"], site_id))
        if checked:
            cur.execute("UPDATE sites SET river_checked_at = now() WHERE id = ANY(%s)", (checked,))
    log.info("river link: %d of %d sites have a flood-staged gauge within %g mi", len(matched), len(checked),
             MATCH_RADIUS_MI)
    return len(matched)


def latest_observed(detail: dict) -> tuple[datetime | None, float | None, float | None]:
    """(time, stage ft, flow cfs) of a gauge's latest observation, from /gauges/{lid}."""
    obs = (detail.get("status") or {}).get("observed") or {}
    stage = _value(obs.get("primary"))
    flow = _value(obs.get("secondary"))
    if flow is not None and (obs.get("secondaryUnit") or "").lower() == "kcfs":
        flow *= 1000
    valid = obs.get("validTime")
    ts = datetime.fromisoformat(valid.replace("Z", "+00:00")) if valid and not valid.startswith("0001") else None
    return ts, stage, flow


def forecast_peak(series: dict, now: datetime, hours: int = FORECAST_HOURS) -> float | None:
    """Highest forecast stage in the next `hours`, from /gauges/{lid}/stageflow/forecast."""
    end = now + timedelta(hours=hours)
    values = []
    for point in series.get("data") or []:
        ts = datetime.fromisoformat(point["validTime"].replace("Z", "+00:00"))
        if now <= ts <= end and (v := _value(point.get("primary"))) is not None:
            values.append(v)
    return max(values, default=None)


UPSERT_LEVEL = """
INSERT INTO river_levels (gauge_id, ts, stage_ft, flow_cfs, forecast_stage_ft, category)
VALUES (%(gauge_id)s, %(ts)s, %(stage)s, %(flow)s, %(forecast)s, %(category)s)
ON CONFLICT (gauge_id, ts) DO UPDATE SET stage_ft = EXCLUDED.stage_ft, flow_cfs = EXCLUDED.flow_cfs,
    forecast_stage_ft = EXCLUDED.forecast_stage_ft, category = EXCLUDED.category
"""


def poll(site_ids: list[int] | None = None) -> int:
    """Link new sites, then read each matched gauge's latest stage and 48 h forecast. Returns gauges read."""
    link_sites(site_ids)
    now = datetime.now(UTC)
    with connection() as conn:
        gauges = conn.execute(
            "SELECT DISTINCT g.gauge_id, g.action_stage_ft, g.flood_stage_ft, g.moderate_stage_ft, g.major_stage_ft "
            "FROM river_gauges g JOIN sites s ON s.usgs_gauge_id = g.gauge_id "
            "WHERE %(ids)s::int[] IS NULL OR s.id = ANY(%(ids)s)", {"ids": site_ids}).fetchall()
    rows = []
    with httpx.Client(timeout=30) as client:
        for g in gauges:
            try:
                ts, stage, flow = latest_observed(_get(client, f"/gauges/{g['gauge_id']}"))
                try:
                    forecast = forecast_peak(_get(client, f"/gauges/{g['gauge_id']}/stageflow/forecast"), now)
                except httpx.HTTPStatusError:
                    forecast = None  # many gauges have no NWS forecast
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                log.warning("NWPS reading failed for gauge %s: %s", g["gauge_id"], exc)
                continue
            if ts is None or stage is None:
                continue
            st = {"action": g["action_stage_ft"], "minor": g["flood_stage_ft"], "moderate": g["moderate_stage_ft"],
                  "major": g["major_stage_ft"]}
            rows.append({"gauge_id": g["gauge_id"], "ts": ts, "stage": stage, "flow": flow, "forecast": forecast,
                         "category": hazards.flood_category(stage, st)})
    if rows:
        with connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.executemany(UPSERT_LEVEL, rows)
    log.info("river poll: %d of %d gauges read", len(rows), len(gauges))
    return len(rows)
