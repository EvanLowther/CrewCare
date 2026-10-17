"""Owner: Person B. Sites managers create, who's on each site, and user roles (docs/AUTH.md).

New sites are private (`is_reference = false`) and the creator becomes their manager. The worker reads the
`sites` table, so a new site gets weather, alerts and scores on its next poll without any worker change.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx
from fastapi import HTTPException
from tzfpy import get_tz

from planit.api.access import can_delete, can_manage, member_role_error
from planit.auth import DEV_SUB_PREFIX, CurrentUser
from planit.config import settings
from planit.db import connection
from planit.models import AdminUser, Me, MySite, SiteCreate, SiteMember, SiteUpdate, User

log = logging.getLogger("planit.sites")

# Tables with a site_id that a deleted site's rows must leave first (sites.id has no ON DELETE CASCADE).
_SITE_CHILD_TABLES = ("hazard_scores", "weather", "nws_weather", "alerts", "nws_alerts", "briefings",
                      "hazard_reports")
# Cleared when a site moves, so the worker looks its NWS grid up again (migration 005).
_NWS_LOOKUP_COLS = ("nws_grid_id", "nws_grid_x", "nws_grid_y", "nws_station", "nws_zone", "nws_county_zone")
UNKNOWN_STATE = "XX"


def _state_for(lat: float, lon: float) -> str:
    """Two-letter state from the NWS points API; 422 outside the US (no NWS forecasts there)."""
    try:
        r = httpx.get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}",
                      headers={"User-Agent": settings.nws_user_agent, "Accept": "application/geo+json"}, timeout=8)
    except httpx.HTTPError:
        log.warning("NWS points lookup failed for %s,%s", lat, lon, exc_info=True)
        return UNKNOWN_STATE
    if r.status_code == 404:
        raise HTTPException(422, "Sites must be in the United States (weather data comes from the NWS)")
    if r.status_code != 200:
        return UNKNOWN_STATE
    rel = r.json().get("properties", {}).get("relativeLocation", {}).get("properties", {})
    return rel.get("state") or UNKNOWN_STATE


def _place(lat: float, lon: float) -> dict:
    return {"lat": lat, "lon": lon, "state": _state_for(lat, lon), "timezone": get_tz(lon, lat) or "America/New_York"}


def _site_access(conn, site_id: int, user: CurrentUser) -> dict:
    row = conn.execute(
        "SELECT s.id, s.name, s.is_reference, s.created_by, m.role AS my_role FROM sites s "
        "LEFT JOIN site_members m ON m.site_id = s.id AND m.user_id = %s WHERE s.id = %s",
        (user.id, site_id),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Site not found")
    return row


def _require_manage(conn, site_id: int, user: CurrentUser) -> dict:
    site = _site_access(conn, site_id, user)
    if not can_manage(user, site["my_role"]):
        raise HTTPException(403, f"Only {site['name']}'s managers can do that")
    return site


# --- Sites ------------------------------------------------------------------

def create_site(req: SiteCreate, user: CurrentUser) -> int:
    place = _place(req.latitude, req.longitude)
    with connection() as conn, conn.transaction():
        site_id = conn.execute(
            "INSERT INTO sites (name, state, latitude, longitude, geom, timezone, description, is_reference, "
            "created_by) VALUES (%(name)s, %(state)s, %(lat)s, %(lon)s, "
            "ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, %(timezone)s, %(description)s, false, "
            "%(user_id)s) RETURNING id",
            {**place, "name": req.name.strip(), "description": (req.description or "").strip() or None,
             "user_id": user.id},
        ).fetchone()["id"]
        conn.execute("INSERT INTO site_members (site_id, user_id, role, added_by) VALUES (%s, %s, 'manager', %s)",
                     (site_id, user.id, user.id))
    return site_id


def update_site(site_id: int, req: SiteUpdate, user: CurrentUser) -> None:
    changes = req.model_dump(exclude_unset=True)
    with connection() as conn, conn.transaction():
        _require_manage(conn, site_id, user)
        current = conn.execute("SELECT latitude, longitude FROM sites WHERE id = %s", (site_id,)).fetchone()
        sets, params = [], {"id": site_id}
        if "name" in changes and changes["name"]:
            sets.append("name = %(name)s")
            params["name"] = changes["name"].strip()
        if "description" in changes:
            sets.append("description = %(description)s")
            params["description"] = (changes["description"] or "").strip() or None
        lat, lon = changes.get("latitude") or current["latitude"], changes.get("longitude") or current["longitude"]
        if (lat, lon) != (current["latitude"], current["longitude"]):
            params.update(_place(lat, lon))
            sets += ["latitude = %(lat)s", "longitude = %(lon)s", "state = %(state)s", "timezone = %(timezone)s",
                     "geom = ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography"]
            sets += [f"{col} = NULL" for col in _NWS_LOOKUP_COLS]
        if sets:
            conn.execute(f"UPDATE sites SET {', '.join(sets)} WHERE id = %(id)s", params)


def delete_site(site_id: int, user: CurrentUser) -> None:
    with connection() as conn, conn.transaction():
        site = _site_access(conn, site_id, user)
        if not can_delete(user, site["my_role"], site["created_by"]):
            raise HTTPException(403, "Only the manager who created this site (or an admin) can delete it")
        if site["is_reference"] and not user.is_admin:
            raise HTTPException(403, "Reference sites can only be deleted by an admin")
        for table in _SITE_CHILD_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE site_id = %s", (site_id,))
        conn.execute("DELETE FROM sites WHERE id = %s", (site_id,))


# --- Members ----------------------------------------------------------------

_MEMBER_SQL = ("SELECT m.user_id, u.name, u.email, m.role, m.added_at FROM site_members m "
               "JOIN users u ON u.id = m.user_id WHERE m.site_id = %s "
               "ORDER BY m.role, lower(coalesce(u.name, u.email))")


def list_members(site_id: int, user: CurrentUser) -> list[SiteMember]:
    with connection() as conn:
        site = _site_access(conn, site_id, user)
        if not (site["my_role"] or user.is_admin):
            raise HTTPException(403, f"You're not on {site['name']}")
        return [SiteMember(**r) for r in conn.execute(_MEMBER_SQL, (site_id,)).fetchall()]


def add_member(site_id: int, member_id: UUID, role: str, user: CurrentUser) -> list[SiteMember]:
    with connection() as conn, conn.transaction():
        _require_manage(conn, site_id, user)
        target = conn.execute("SELECT role FROM users WHERE id = %s", (member_id,)).fetchone()
        if target is None:
            raise HTTPException(404, "User not found")
        problem = member_role_error(target["role"], role)
        if problem:
            raise HTTPException(422, problem)
        conn.execute(
            "INSERT INTO site_members (site_id, user_id, role, added_by) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (site_id, user_id) DO UPDATE SET role = EXCLUDED.role",
            (site_id, member_id, role, user.id),
        )
        return [SiteMember(**r) for r in conn.execute(_MEMBER_SQL, (site_id,)).fetchall()]


def remove_member(site_id: int, member_id: UUID, user: CurrentUser) -> list[SiteMember]:
    with connection() as conn, conn.transaction():
        site = _require_manage(conn, site_id, user)
        managers = [r["user_id"] for r in conn.execute(
            "SELECT user_id FROM site_members WHERE site_id = %s AND role = 'manager'", (site_id,)).fetchall()]
        if managers == [member_id] and not site["is_reference"] and not user.is_admin:
            raise HTTPException(409, "A site needs at least one manager. Add another manager first.")
        conn.execute("DELETE FROM site_members WHERE site_id = %s AND user_id = %s", (site_id, member_id))
        return [SiteMember(**r) for r in conn.execute(_MEMBER_SQL, (site_id,)).fetchall()]


# --- Users ------------------------------------------------------------------

def _hide_dev_users() -> str:
    return "" if settings.auth_dev else f" AND u.auth0_sub NOT LIKE '{DEV_SUB_PREFIX}%%'"


def search_users(q: str, limit: int = 20) -> list[User]:
    """People who have signed up, by name or email, for a manager adding crew."""
    pattern = f"%{q.strip()}%"
    with connection() as conn:
        rows = conn.execute(
            "SELECT u.id, u.name, u.email, u.picture, u.role FROM users u "
            "WHERE (u.name ILIKE %(p)s OR u.email ILIKE %(p)s)" + _hide_dev_users() +
            " ORDER BY lower(coalesce(u.name, u.email)) LIMIT %(limit)s",
            {"p": pattern, "limit": limit},
        ).fetchall()
    return [User(**r) for r in rows]


def me(user: CurrentUser | None) -> Me:
    auth = "dev" if settings.auth_dev else "auth0"
    if user is None:
        return Me(user=None, sites=[], auth=auth)
    with connection() as conn:
        rows = conn.execute(
            "SELECT m.site_id, s.name AS site_name, m.role FROM site_members m JOIN sites s ON s.id = m.site_id "
            "WHERE m.user_id = %s ORDER BY s.name", (user.id,)).fetchall()
    return Me(user=User(id=user.id, name=user.name, email=user.email, picture=user.picture, role=user.role),
              sites=[MySite(**r) for r in rows], auth=auth)


def list_users() -> list[AdminUser]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT u.id, u.name, u.email, u.picture, u.role, u.created_at, u.last_seen_at, "
            "count(m.site_id) AS site_count FROM users u LEFT JOIN site_members m ON m.user_id = u.id "
            "WHERE TRUE" + _hide_dev_users() + " GROUP BY u.id ORDER BY u.created_at DESC").fetchall()
    return [AdminUser(**r) for r in rows]


def set_role(target_id: UUID, role: str, admin: CurrentUser) -> AdminUser:
    """Change someone's role. Demoting a manager to crew also makes them crew on the sites they managed."""
    if target_id == admin.id and role != "admin":
        raise HTTPException(409, "You can't remove your own admin role")
    with connection() as conn, conn.transaction():
        if conn.execute("UPDATE users SET role = %s WHERE id = %s", (role, target_id)).rowcount == 0:
            raise HTTPException(404, "User not found")
        if role == "crew":
            conn.execute("UPDATE site_members SET role = 'crew' WHERE user_id = %s", (target_id,))
    return next(u for u in list_users() if u.id == target_id)

