"""Owner: Person B. Crew hazard reports: save (with photo), list and resolve.

A report is filed on a site the reporter belongs to, from within 5 miles of it (planit/api/access.py), and expires
after a time that depends on the hazard (a gator moves on; a washed-out road stays until someone resolves it).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException

from planit.api.access import can_manage, can_report, report_location_error, signed_photo_url, visible_sites_sql
from planit.auth import CurrentUser
from planit.db import connection
from planit.models import HazardReport
from planit.storage.photos import save_photo

# How long a report stays on the map unless resolved first. None = until resolved.
EXPIRES_AFTER: dict[str, timedelta | None] = {
    "wildlife": timedelta(hours=48),
    "heat_illness": timedelta(hours=12),
    "flooding": timedelta(hours=24),
    "fire": timedelta(hours=24),
    "downed_line": None,
    "unstable_ground": timedelta(days=7),
    "other": timedelta(hours=72),
    "lightning": timedelta(hours=1),        # thunder heard: the 30-minute rule, with room to spare
    "high_wind": timedelta(hours=6),
    "ice": timedelta(hours=24),
    "snow": timedelta(hours=48),
    "cold_stress": timedelta(hours=12),
    "smoke": timedelta(hours=12),
    "sinkhole": None,
    "fallen_tree": None,
    "gas_leak": None,
    "earthquake_damage": None,
}

_REPORT_COLS = ("r.id, r.site_id, r.latitude, r.longitude, r.hazard_type, r.severity, r.description, "
                "r.reporter_name, r.photo_id, r.status, r.created_at, r.expires_at, r.resolved_at, r.confirmed_at, "
                "(SELECT coalesce(u.name, u.email) FROM users u WHERE u.id = r.confirmed_by) AS confirmed_by_name")


def _report(row: dict) -> HazardReport:
    photo_id = row.pop("photo_id")
    return HazardReport(**row, photo_url=signed_photo_url(photo_id) if photo_id else None)


def _site_for(conn, site_id: int, user: CurrentUser) -> dict:
    site = conn.execute(
        "SELECT s.id, s.name, s.latitude, s.longitude, s.is_reference, m.role AS my_role FROM sites s "
        "LEFT JOIN site_members m ON m.site_id = s.id AND m.user_id = %s WHERE s.id = %s",
        (user.id, site_id),
    ).fetchone()
    if site is None:
        raise HTTPException(404, "Site not found")
    return site


def create_report(*, user: CurrentUser, site_id: int, latitude: float, longitude: float,
                  gps: tuple[float, float] | None, gps_accuracy_m: float | None, hazard_type: str, severity: str,
                  description: str | None, photo: bytes | None) -> HazardReport:
    """Files a report on `site_id`. Members only, with their phone and the pin within 5 miles; admins anywhere."""
    with connection() as conn:
        site = _site_for(conn, site_id, user)
    if not can_report(user, site["my_role"]):
        raise HTTPException(403, f"You're not on {site['name']}. Ask its manager to add you.")
    if not user.is_admin:
        problem = report_location_error(site["latitude"], site["longitude"], site["name"], (latitude, longitude),
                                        gps)
        if problem:
            raise HTTPException(403, problem)

    photo_id: UUID | None = save_photo(photo) if photo else None
    ttl = EXPIRES_AFTER.get(hazard_type)
    expires_at = datetime.now(UTC) + ttl if ttl else None
    with connection() as conn:
        row = conn.execute(
            "INSERT INTO hazard_reports (site_id, latitude, longitude, geom, hazard_type, severity, description, "
            "reporter_name, reporter_id, gps_latitude, gps_longitude, gps_accuracy_m, photo_id, expires_at) "
            "VALUES (%(site_id)s, %(lat)s, %(lon)s, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, "
            "%(hazard_type)s, %(severity)s, %(description)s, %(reporter_name)s, %(reporter_id)s, %(gps_lat)s, "
            "%(gps_lon)s, %(gps_acc)s, %(photo_id)s, %(expires_at)s) "
            f"RETURNING {_REPORT_COLS.replace('r.', '')}",
            {"site_id": site_id, "lat": latitude, "lon": longitude, "hazard_type": hazard_type,
             "severity": severity, "description": description, "reporter_name": user.display_name,
             "reporter_id": user.id, "gps_lat": gps[0] if gps else None, "gps_lon": gps[1] if gps else None,
             "gps_acc": gps_accuracy_m, "photo_id": photo_id, "expires_at": expires_at},
        ).fetchone()
    return _report(dict(row))


def list_reports(site_id: int | None = None, user: CurrentUser | None = None, include_past: bool = False
                 ) -> list[HazardReport]:
    """Active, unexpired reports on sites `user` may see (plus legacy ones with no site), newest first; with
    `site_id`, only those filed on that site. `include_past` (with a site) adds resolved and expired ones."""
    visible, params = visible_sites_sql(user)
    current = "" if include_past else "r.status = 'active' AND (r.expires_at IS NULL OR r.expires_at > now()) AND "
    sql = (f"SELECT {_REPORT_COLS} FROM hazard_reports r LEFT JOIN sites s ON s.id = r.site_id "
           f"WHERE {current}(s.id IS NULL OR {visible})")
    if site_id is not None:
        sql += " AND r.site_id = %(site_id)s"
        params["site_id"] = site_id
    with connection() as conn:
        rows = conn.execute(sql + " ORDER BY r.created_at DESC LIMIT 200", params).fetchall()
    return [_report(dict(r)) for r in rows]


def resolve_report(report_id: UUID, user: CurrentUser) -> HazardReport:
    """Marks a report resolved so it leaves the map. The site's managers and admins only."""
    with connection() as conn:
        found = conn.execute(
            "SELECT r.site_id, m.role AS my_role FROM hazard_reports r "
            "LEFT JOIN site_members m ON m.site_id = r.site_id AND m.user_id = %s WHERE r.id = %s",
            (user.id, report_id),
        ).fetchone()
        if found is None:
            raise HTTPException(404, "Report not found")
        if not can_manage(user, found["my_role"]):
            raise HTTPException(403, "Only this site's managers can resolve its reports")
        row = conn.execute(
            "UPDATE hazard_reports SET status = 'resolved', resolved_by = %s, resolved_at = now() WHERE id = %s "
            f"RETURNING {_REPORT_COLS.replace('r.', '')}",
            (user.id, report_id),
        ).fetchone()
    return _report(dict(row))


def confirm_report(report_id: UUID, user: CurrentUser) -> HazardReport:
    """Marks a report confirmed: it counts fully in the score (hazards.crew_report). The site's managers and admins."""
    with connection() as conn:
        found = conn.execute(
            "SELECT r.site_id, m.role AS my_role FROM hazard_reports r "
            "LEFT JOIN site_members m ON m.site_id = r.site_id AND m.user_id = %s WHERE r.id = %s",
            (user.id, report_id),
        ).fetchone()
        if found is None:
            raise HTTPException(404, "Report not found")
        if not can_manage(user, found["my_role"]):
            raise HTTPException(403, "Only this site's managers can confirm its reports")
        row = conn.execute(
            "UPDATE hazard_reports SET confirmed_by = %s, confirmed_at = coalesce(confirmed_at, now()) WHERE id = %s "
            f"RETURNING {_REPORT_COLS.replace('r.', '')}",
            (user.id, report_id),
        ).fetchone()
    return _report(dict(row))


def photo_visible(photo_id: UUID, user: CurrentUser | None) -> bool:
    """Whether the photo belongs to a report `user` may see (used by the unsigned fallback)."""
    visible, params = visible_sites_sql(user)
    with connection() as conn:
        return conn.execute(
            "SELECT 1 FROM hazard_reports r LEFT JOIN sites s ON s.id = r.site_id "
            f"WHERE r.photo_id = %(photo_id)s AND (s.id IS NULL OR {visible})",
            {"photo_id": photo_id, **params},
        ).fetchone() is not None
