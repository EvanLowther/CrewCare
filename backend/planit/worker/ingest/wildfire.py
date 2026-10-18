"""Owner: Person A. Active wildfires near a site -> app `alerts` (type 'wildfire').

Source: NIFC's WFIGS "Incident Locations Current" layer (https://data-nifc.opendata.arcgis.com, no key): every
wildfire US agencies are working that isn't declared out, with its point of origin, acres and % contained. One
national query per poll. Fires are reported by people, so a new fire can take hours to appear.

For each site, hazards.wildfire() scores every fire whose estimated edge is within 25 miles (under 100 acres: 10,
spot fires: 5); small fires still listed 3 days after they were found are skipped as stale records. Each becomes an
alert with dedupe_key = the fire's IRWIN id and meta.rule_severity / meta.action for the scorer. Alerts
clear when NIFC stops listing the fire, it moves out of range or it reaches 100% containment, but only after a
successful request, so a network blip never clears a real fire.
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

QUERY_URL = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
             "WFIGS_Incident_Locations_Current/FeatureServer/0/query")
FIELDS = ("IncidentName", "IncidentSize", "PercentContained", "IrwinID", "UniqueFireIdentifier",
          "FireDiscoveryDateTime", "POOState")
PAGE_SIZE = 2000  # the layer's maxRecordCount
SOURCE = "nifc"
# A small fire (under hazards.SMALL_FIRE_ACRES) still listed days after it was found is a record nobody closed, not a
# threat: dozens linger for months with no size.
STALE_SMALL_FIRE = timedelta(days=3)


def fetch_fires(client: httpx.Client) -> list[dict]:
    """Every current wildfire (IncidentTypeCategory 'WF'; prescribed burns are 'RX'), as GeoJSON features."""
    features, offset = [], 0
    while True:
        resp = client.get(QUERY_URL, params={
            "where": "IncidentTypeCategory = 'WF'", "outFields": ",".join(FIELDS), "f": "geojson",
            "resultOffset": offset, "resultRecordCount": PAGE_SIZE, "orderByFields": "OBJECTID",
        })
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:  # ArcGIS reports errors with HTTP 200
            raise httpx.HTTPError(f"NIFC query error: {data['error']}")
        page = data.get("features", [])
        features += page
        if not (data.get("properties") or {}).get("exceededTransferLimit") and len(page) < PAGE_SIZE:
            return features
        offset += len(page)


def fires(features: list[dict], now: datetime) -> list[dict]:
    """Fires from the NIFC features, without stale small ones."""
    out = []
    for f in features:
        p, coords = f["properties"], (f.get("geometry") or {}).get("coordinates")
        key = p.get("IrwinID") or p.get("UniqueFireIdentifier")
        if not coords or not key:
            continue
        found = p.get("FireDiscoveryDateTime")
        discovered = datetime.fromtimestamp(found / 1000, UTC) if found else None
        small = (p.get("IncidentSize") or 0.0) < hazards.SMALL_FIRE_ACRES
        if small and discovered and now - discovered > STALE_SMALL_FIRE:
            continue
        out.append({"id": key, "name": p.get("IncidentName") or "Unnamed", "acres": p.get("IncidentSize"),
                    "contained_pct": p.get("PercentContained"), "longitude": coords[0], "latitude": coords[1],
                    "discovered": discovered})
    return out


def alert_row(site: dict, fire: dict) -> dict | None:
    """The app alert for one fire at one site, or None when it's out of range or contained."""
    miles = hazards.miles_between(site["latitude"], site["longitude"], fire["latitude"], fire["longitude"])
    hazard = hazards.wildfire(fire["name"], miles, fire["acres"], fire["contained_pct"])
    if hazard is None:
        return None
    found = fire["discovered"]
    since = f" Discovered {found:%b} {found.day}." if found else ""
    return {
        "site_id": site["id"],
        "type": "wildfire",
        "severity": hazards.badge_for(hazard.severity),
        "title": hazard.label,
        "message": f"{hazard.action or 'Watch for smoke and road closures'}.{since} Source: NIFC.",
        "started_at": fire["discovered"] or datetime.now(UTC),
        "dedupe_key": fire["id"],
        "meta": Jsonb({"source": SOURCE, "incident": fire["name"], "acres": fire["acres"],
                       "contained_pct": fire["contained_pct"], "distance_mi": round(miles, 1),
                       "edge_mi": round(hazards.fire_edge_mi(miles, fire["acres"]), 1),
                       "rule_severity": round(hazard.severity, 1), "action": hazard.action}),
    }


def alerts_for(sites: list[dict], features: list[dict], now: datetime) -> dict[int, list[dict]]:
    """Alerts per site (every site gets a list, so fires that are gone can be cleared)."""
    current = fires(features, now)
    return {s["id"]: [r for f in current if (r := alert_row(s, f)) is not None] for s in sites}


def poll() -> int:
    """Fetch current wildfires and raise or clear wildfire alerts. Returns the number of active fire alerts."""
    with connection() as conn:
        sites = conn.execute("SELECT id, latitude, longitude FROM sites ORDER BY id").fetchall()
    try:
        with httpx.Client(timeout=60) as client:
            features = fetch_fires(client)
    except httpx.HTTPError as exc:
        log.warning("NIFC wildfire request failed: %s", exc)
        return 0

    per_site = alerts_for(sites, features, datetime.now(UTC))
    with connection() as conn, conn.transaction(), conn.cursor() as cur:
        for site_id, rows in per_site.items():
            if rows:
                cur.executemany(UPSERT_APP, rows)
            cur.execute(CLEAR_GONE, {"source": SOURCE, "site_id": site_id, "keep": [r["dedupe_key"] for r in rows]})
    active = sum(len(rows) for rows in per_site.values())
    log.info("wildfire: %d current fires, %d site alerts", len(features), active)
    return active
