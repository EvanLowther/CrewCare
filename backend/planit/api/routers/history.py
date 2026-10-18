"""Owner: Person B. Past hazards near a site or a spot on the map (crew reports and NOAA Storm Events)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from planit.api import history_store, mock
from planit.api.access import visible_sites_sql
from planit.api.deps import use_mock
from planit.auth import ManagerUser, OptionalUser
from planit.db import connection
from planit.models import LocationHistory

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/sites/{site_id}/history", response_model=LocationHistory)
def site_history(site_id: int, user: OptionalUser) -> LocationHistory:
    """Crew reports within 5 mi of the site (resolved and expired too) and NOAA Storm Events within 25 mi."""
    if use_mock():
        return mock.location_history()
    visible, params = visible_sites_sql(user)
    with connection() as conn:
        site = conn.execute(f"SELECT s.latitude, s.longitude, {visible} AS ok FROM sites s WHERE s.id = %(id)s",
                            {"id": site_id, **params}).fetchone()
    if site is None:
        raise HTTPException(404, "Site not found")
    if not site["ok"]:
        raise HTTPException(403, "You're not on this site")
    return history_store.location_history(site["latitude"], site["longitude"], user)


@router.get("/history", response_model=LocationHistory)
def place_history(user: ManagerUser, lat: Annotated[float, Query(ge=-90, le=90)],
                  lon: Annotated[float, Query(ge=-180, le=180)]) -> LocationHistory:
    """The same for any spot, for the new-site form (managers and admins)."""
    if use_mock():
        return mock.location_history()
    return history_store.location_history(lat, lon, user)
