"""Owner: Person B. Crew hazard reports: save (with photo) and list.

The API writes only `hazard_reports` and `photos` (see docs/ARCHITECTURE.md). A report is tied to the nearest
site within NEAREST_SITE_MI, and expires after a time that depends on the hazard (a gator moves on; a washed-out
road stays until someone resolves it).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from planit.db import connection
from planit.models import HazardReport
from planit.storage.photos import save_photo

NEAREST_SITE_MI = 10.0
METERS_PER_MILE = 1609.34

# How long a report stays on the map unless resolved first. None = until resolved.
EXPIRES_AFTER: dict[str, timedelta | None] = {
    "wildlife": timedelta(hours=48),
    "heat_illness": timedelta(hours=12),
    "flooding": timedelta(hours=24),
    "fire": timedelta(hours=24),
    "downed_line": None,
    "unstable_ground": timedelta(days=7),
    "other": timedelta(hours=72),
}

_REPORT_COLS = ("r.id, r.site_id, r.latitude, r.longitude, r.hazard_type, r.severity, r.description, "
                "r.reporter_name, r.photo_id, r.status, r.created_at, r.expires_at")


def _report(row: dict) -> HazardReport:
    photo_id = row.pop("photo_id")
    return HazardReport(**row, photo_url=f"/api/photos/{photo_id}" if photo_id else None)


def nearest_site(conn, latitude: float, longitude: float) -> int | None:
    row = conn.execute(
        "SELECT id FROM sites "
        "WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, %(radius)s) "
        "ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography LIMIT 1",
        {"lat": latitude, "lon": longitude, "radius": NEAREST_SITE_MI * METERS_PER_MILE},
    ).fetchone()
    return row["id"] if row else None


def create_report(*, latitude: float, longitude: float, hazard_type: str, severity: str,
                  description: str | None, reporter_name: str | None, photo: bytes | None) -> HazardReport:
    photo_id: UUID | None = save_photo(photo) if photo else None
    ttl = EXPIRES_AFTER.get(hazard_type)
    expires_at = datetime.now(UTC) + ttl if ttl else None
    with connection() as conn, conn.transaction():
        site_id = nearest_site(conn, latitude, longitude)
        row = conn.execute(
            "INSERT INTO hazard_reports (site_id, latitude, longitude, geom, hazard_type, severity, description, "
            "reporter_name, photo_id, expires_at) VALUES (%(site_id)s, %(lat)s, %(lon)s, "
            "ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, %(hazard_type)s, %(severity)s, "
            "%(description)s, %(reporter_name)s, %(photo_id)s, %(expires_at)s) "
            f"RETURNING {_REPORT_COLS.replace('r.', '')}",
            {"site_id": site_id, "lat": latitude, "lon": longitude, "hazard_type": hazard_type,
             "severity": severity, "description": description, "reporter_name": reporter_name,
             "photo_id": photo_id, "expires_at": expires_at},
        ).fetchone()
    return _report(dict(row))


def list_reports(site_id: int | None = None) -> list[HazardReport]:
    """Active, unexpired reports, newest first; with `site_id`, only those tied to that site."""
    sql = (f"SELECT {_REPORT_COLS} FROM hazard_reports r "
           "WHERE r.status = 'active' AND (r.expires_at IS NULL OR r.expires_at > now())")
    params: dict = {}
    if site_id is not None:
        sql += " AND r.site_id = %(site_id)s"
        params["site_id"] = site_id
    with connection() as conn:
        rows = conn.execute(sql + " ORDER BY r.created_at DESC LIMIT 200", params).fetchall()
    return [_report(dict(r)) for r in rows]
