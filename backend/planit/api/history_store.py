"""Owner: Person B. Past hazards near a place, "a database of location hazards for future project owners".

For a site page or a spot on the new-site map: crew reports filed within 5 miles (resolved and expired ones too,
on sites the viewer may see) and NOAA Storm Events within 25 miles (located events only; NOAA logs about 40%
by county or forecast zone with no point, so those can't be placed). The radii match the report rule and the
model's labels.
"""

from __future__ import annotations

import math
from functools import lru_cache

from planit.api.access import visible_sites_sql
from planit.auth import CurrentUser
from planit.db import connection
from planit.models import EventTypeCount, LocationHistory, PastReport, PastStormEvent

REPORT_RADIUS_MI = 5.0
STORM_RADIUS_MI = 25.0
M_PER_MI = 1609.344
LIST_LIMIT = 50

# storm_events has no geometry column; a lat/lon box (25 mi is ~0.37° of latitude, and 0.37° / cos(latitude) of
# longitude) narrows it before measuring the real distance.
_STORM_SQL = """
WITH p AS (SELECT ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography AS g),
near AS (
    SELECT e.event_id, e.event_type, e.begin_ts, e.cz_name, e.state, coalesce(e.injuries, 0) AS injuries,
           coalesce(e.deaths, 0) AS deaths, coalesce(e.damage_usd, 0) AS damage_usd,
           ST_Distance(ST_SetSRID(ST_MakePoint(e.longitude, e.latitude), 4326)::geography, p.g) / %(m_per_mi)s
               AS distance_mi
    FROM storm_events e, p
    WHERE e.latitude BETWEEN %(lat)s - 0.4 AND %(lat)s + 0.4
      AND e.longitude BETWEEN %(lon)s - %(dlon)s AND %(lon)s + %(dlon)s
      AND ST_DWithin(ST_SetSRID(ST_MakePoint(e.longitude, e.latitude), 4326)::geography, p.g, %(radius_m)s)
)
SELECT * FROM near
"""


@lru_cache(maxsize=1)
def _storm_years() -> str:
    with connection() as conn:
        row = conn.execute("SELECT min(extract(year FROM begin_ts))::int AS lo, "
                           "max(extract(year FROM begin_ts))::int AS hi FROM storm_events "
                           "WHERE begin_ts < date_trunc('year', now())").fetchone()
    if not row or row["lo"] is None:
        return "none loaded"
    return str(row["lo"]) if row["lo"] == row["hi"] else f"{row['lo']}-{row['hi']}"


def _years(totals: list[dict]) -> str | None:
    """The years the nearby events span (NOAA's coverage differs by state: Florida from 2023, the rest 2024)."""
    if not totals:
        return None
    lo, hi = min(t["first"].year for t in totals), max(t["last"].year for t in totals)
    return str(lo) if lo == hi else f"{lo}-{hi}"


def _title_case(place: str | None) -> str | None:
    return place.title() if place else None


def location_history(lat: float, lon: float, user: CurrentUser | None) -> LocationHistory:
    visible, vis_params = visible_sites_sql(user, alias="rs")
    with connection() as conn:
        reports = conn.execute(
            "SELECT r.id, r.site_id, rs.name AS site_name, r.hazard_type, r.severity, r.description, r.created_at, "
            "CASE WHEN r.status = 'resolved' THEN 'resolved' "
            "     WHEN r.expires_at IS NOT NULL AND r.expires_at <= now() THEN 'expired' ELSE 'active' END AS status, "
            "ST_Distance(r.geom, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography) / %(m_per_mi)s "
            "    AS distance_mi "
            "FROM hazard_reports r LEFT JOIN sites rs ON rs.id = r.site_id "
            "WHERE ST_DWithin(r.geom, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, %(radius_m)s) "
            f"AND (rs.id IS NULL OR {visible}) "
            "ORDER BY r.created_at DESC LIMIT %(limit)s",
            {"lat": lat, "lon": lon, "m_per_mi": M_PER_MI, "radius_m": REPORT_RADIUS_MI * M_PER_MI,
             "limit": LIST_LIMIT, **vis_params},
        ).fetchall()

        storm_params = {"lat": lat, "lon": lon, "m_per_mi": M_PER_MI, "radius_m": STORM_RADIUS_MI * M_PER_MI,
                        "dlon": 0.4 / max(math.cos(math.radians(lat)), 0.2)}
        events = conn.execute(_STORM_SQL + " ORDER BY begin_ts DESC LIMIT %(limit)s",
                              {**storm_params, "limit": LIST_LIMIT}).fetchall()
        totals = conn.execute(
            _STORM_SQL.replace("SELECT * FROM near", "SELECT event_type, count(*) AS count, min(begin_ts) AS first, "
                               "max(begin_ts) AS last FROM near GROUP BY event_type ORDER BY count DESC, event_type"),
            storm_params,
        ).fetchall()

    return LocationHistory(
        report_radius_mi=REPORT_RADIUS_MI,
        storm_radius_mi=STORM_RADIUS_MI,
        reports=[PastReport(**{**r, "distance_mi": round(r["distance_mi"], 1)}) for r in reports],
        storm_events=[
            PastStormEvent(
                event_id=e["event_id"], event_type=e["event_type"], begin_ts=e["begin_ts"],
                place=", ".join(p for p in (_title_case(e["cz_name"]), _title_case(e["state"])) if p) or None,
                distance_mi=round(e["distance_mi"], 1), injuries=e["injuries"], deaths=e["deaths"],
                damage_usd=e["damage_usd"],
            )
            for e in events
        ],
        storm_event_count=sum(t["count"] for t in totals),
        storm_event_types=[EventTypeCount(event_type=t["event_type"], count=t["count"]) for t in totals],
        storm_years=_years(totals) or _storm_years(),
    )
