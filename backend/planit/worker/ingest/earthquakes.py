"""Owner: Person A. Earthquakes felt at a site -> app `alerts` (type 'earthquake').

Feed: https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson (USGS, no key, updated every
minute): every M2.5+ quake of the last day, worldwide, in one request.

For each quake and site, hazards.earthquake_mmi() estimates the shaking at the site (Atkinson & Wald 2007, the
California coefficients west of the Rockies, the central/eastern US ones east). From MMI IV (light: felt indoors by
many) the site gets an 'earthquake' alert, scored by hazards.earthquake(), with dedupe_key = the USGS event id and
meta.rule_severity / meta.action for the scorer. It stays in force for QUAKE_ALERT_HOURS (inspections and
aftershocks): meta.ends tells the scorer when it stops counting, and this job clears it then, or sooner if USGS
deletes the event. A failed request clears nothing.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
from psycopg.types.json import Jsonb

from planit import hazards
from planit.db import connection
from planit.worker.ingest.nws import CLEAR_GONE, UPSERT_APP

log = logging.getLogger(__name__)

FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
SOURCE = "usgs"
QUAKE_ALERT_HOURS = 12
# Even an M8 isn't felt at MMI IV 1,000 mi away (AW07 gives II-III), so farther quakes are skipped early.
MAX_DISTANCE_MI = 1000.0


def quakes(geojson: dict) -> list[dict]:
    """Earthquakes from the USGS feed (quarry blasts, explosions and events without a magnitude are dropped)."""
    out = []
    for f in geojson.get("features", []):
        p, coords = f["properties"], (f.get("geometry") or {}).get("coordinates")
        if p.get("type") != "earthquake" or p.get("mag") is None or not coords:
            continue
        out.append({"id": f["id"], "magnitude": float(p["mag"]), "place": p.get("place") or "unknown location",
                    "time": datetime.fromtimestamp(p["time"] / 1000, UTC), "url": p.get("url"),
                    "longitude": coords[0], "latitude": coords[1], "depth_km": max(0.0, coords[2] or 0.0)})
    return out


def alert_row(site: dict, quake: dict) -> dict | None:
    """The app alert for one quake at one site, or None when the shaking there is below MMI IV."""
    miles = hazards.miles_between(site["latitude"], site["longitude"], quake["latitude"], quake["longitude"])
    if miles > MAX_DISTANCE_MI:
        return None
    mmi = hazards.earthquake_mmi(quake["magnitude"], miles * hazards.KM_PER_MILE, quake["depth_km"],
                                 hazards.quake_region(quake["longitude"]))
    hazard = hazards.earthquake(quake["magnitude"], miles, mmi)
    if hazard is None:
        return None
    ends = quake["time"] + timedelta(hours=QUAKE_ALERT_HOURS)
    return {
        "site_id": site["id"],
        "type": "earthquake",
        "severity": hazards.badge_for(hazard.severity),
        "title": hazard.label,
        "message": (f"M{quake['magnitude']:.1f}, {quake['place']}, {quake['depth_km']:.0f} km deep, at "
                    f"{quake['time']:%H:%M} UTC. Estimated shaking at the site: {hazards.mmi_roman(mmi)}. "
                    f"{hazard.action}."),
        "started_at": quake["time"],
        "dedupe_key": quake["id"],
        "meta": Jsonb({"source": SOURCE, "magnitude": quake["magnitude"], "place": quake["place"],
                       "distance_mi": round(miles, 1), "depth_km": quake["depth_km"], "mmi": round(mmi, 1),
                       "rule_severity": round(hazard.severity, 1), "action": hazard.action,
                       "ends": ends.isoformat(), "url": quake["url"]}),
    }


def alerts_for(sites: list[dict], geojson: dict, now: datetime) -> dict[int, list[dict]]:
    """Alerts still in force at `now`, per site (every site gets a list, so gone ones can be cleared)."""
    recent = [q for q in quakes(geojson) if q["time"] + timedelta(hours=QUAKE_ALERT_HOURS) > now]
    return {s["id"]: [r for q in recent if (r := alert_row(s, q)) is not None] for s in sites}


def poll() -> int:
    """Fetch the USGS feed and raise or clear earthquake alerts. Returns the number of active quake alerts."""
    with connection() as conn:
        sites = conn.execute("SELECT id, latitude, longitude FROM sites ORDER BY id").fetchall()
    try:
        resp = httpx.get(FEED_URL, timeout=60)
        resp.raise_for_status()
        geojson = resp.json()
    except httpx.HTTPError as exc:
        log.warning("USGS earthquake feed failed: %s", exc)
        return 0

    per_site = alerts_for(sites, geojson, datetime.now(UTC))
    with connection() as conn, conn.transaction(), conn.cursor() as cur:
        for site_id, rows in per_site.items():
            if rows:
                cur.executemany(UPSERT_APP, rows)
            cur.execute(CLEAR_GONE, {"source": SOURCE, "site_id": site_id, "keep": [r["dedupe_key"] for r in rows]})
    active = sum(len(rows) for rows in per_site.values())
    log.info("earthquakes: %d quakes in the feed, %d site alerts", len(geojson.get("features", [])), active)
    return active
