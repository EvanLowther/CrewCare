"""Owner: Person B. Who may see and do what (the table in docs/AUTH.md).

Plain functions so the rules are tested without a database. Queries use `visible_sites_sql` to filter rows.

- Everyone, even signed out, sees reference sites (the public EIA plants).
- Members (crew or manager) also see the private sites they're on. Admins see everything.
- A site's managers edit it, add and remove members, and resolve its reports; the manager who created a site may
  delete it. Admins may do all of that anywhere.
- Members report hazards on their sites from within REPORT_RADIUS_MI; admins report anywhere.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import time
from uuid import UUID

from planit.auth import CurrentUser
from planit.config import settings

REPORT_RADIUS_MI = 5.0
EARTH_RADIUS_MI = 3958.8
PHOTO_URL_TTL_S = 24 * 3600


def visible_sites_sql(user: CurrentUser | None, alias: str = "s") -> tuple[str, dict]:
    """A WHERE condition (and its named parameters) for the sites `user` may see."""
    if user is not None and user.is_admin:
        return "TRUE", {}
    if user is None:
        return f"{alias}.is_reference", {}
    return (f"({alias}.is_reference OR EXISTS (SELECT 1 FROM site_members vm_ WHERE vm_.site_id = {alias}.id "
            f"AND vm_.user_id = %(viewer_id)s))", {"viewer_id": user.id})


def can_view(user: CurrentUser | None, is_reference: bool, my_role: str | None) -> bool:
    return is_reference or my_role is not None or (user is not None and user.is_admin)


def can_manage(user: CurrentUser | None, my_role: str | None) -> bool:
    return user is not None and (user.is_admin or my_role == "manager")


def can_delete(user: CurrentUser | None, my_role: str | None, created_by: UUID | None) -> bool:
    return user is not None and (user.is_admin or (my_role == "manager" and created_by == user.id))


def can_report(user: CurrentUser | None, my_role: str | None) -> bool:
    return user is not None and (user.is_admin or my_role in ("manager", "crew"))


def member_role_error(target_user_role: str, member_role: str) -> str | None:
    """Why `target` can't be added with `member_role`, or None if they can."""
    if member_role == "manager" and target_user_role == "crew":
        return "Only managers can manage a site. Ask an admin to make them a manager first."
    return None


def miles_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


def report_location_error(site_lat: float, site_lon: float, site_name: str, pin: tuple[float, float],
                          gps: tuple[float, float] | None) -> str | None:
    """Why a report can't be filed at this spot, or None. The phone's GPS fix and the pin must both be within
    REPORT_RADIUS_MI of the site. (A browser can't prove its GPS is real; this catches mistakes, not cheats.)"""
    if gps is None:
        return "Turn on location so we can confirm you're at the site."
    away = miles_between(gps[0], gps[1], site_lat, site_lon)
    if away > REPORT_RADIUS_MI:
        return f"You need to be within {REPORT_RADIUS_MI:g} miles of {site_name} to report (you're {away:.1f} mi away)."
    if miles_between(pin[0], pin[1], site_lat, site_lon) > REPORT_RADIUS_MI:
        return f"Put the pin within {REPORT_RADIUS_MI:g} miles of {site_name}."
    return None


# --- Photo links ------------------------------------------------------------
# <img> tags can't send the sign-in token, so a photo URL carries a signature instead. The API only hands out
# signed URLs for reports the viewer may see. Expiry is rounded to the hour so browsers can cache the image.

def _photo_sig(photo_id: UUID, exp: int) -> str:
    msg = f"{photo_id}:{exp}".encode()
    return hmac.new(settings.photo_signing_key.encode(), msg, hashlib.sha256).hexdigest()[:32]


def signed_photo_url(photo_id: UUID, now: float | None = None) -> str:
    exp = (int((now or time.time()) + PHOTO_URL_TTL_S) // 3600 + 1) * 3600
    return f"/api/photos/{photo_id}?exp={exp}&sig={_photo_sig(photo_id, exp)}"


def photo_signature_ok(photo_id: UUID, exp: int, sig: str, now: float | None = None) -> bool:
    return exp >= (now or time.time()) and hmac.compare_digest(sig, _photo_sig(photo_id, exp))
