"""Owner: Person B. Address search for placing a new site (OpenStreetMap Nominatim, US only).

Nominatim is free with no key, for light use: at most one request a second and a real User-Agent. The new-site
form only searches when someone presses Find, and repeat searches are served from a small cache.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import httpx
from fastapi import HTTPException

from planit.models import GeocodeResult

log = logging.getLogger("planit.geocode")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim refuses placeholder contacts (like the example.com one in .env.example), so name the project instead.
USER_AGENT = "CrewCare/1.0 (+https://github.com/EvanLowther/planit-control)"


@lru_cache(maxsize=256)
def _search(query: str) -> tuple[GeocodeResult, ...]:
    r = httpx.get(NOMINATIM_URL, params={"q": query, "format": "jsonv2", "countrycodes": "us", "limit": 5},
                  headers={"User-Agent": USER_AGENT}, timeout=8)
    r.raise_for_status()
    return tuple(GeocodeResult(label=hit["display_name"], latitude=float(hit["lat"]), longitude=float(hit["lon"]))
                 for hit in r.json())


def search(query: str) -> list[GeocodeResult]:
    try:
        return list(_search(" ".join(query.split()).lower()))
    except httpx.HTTPError:
        log.warning("Address lookup failed for %r", query, exc_info=True)
        raise HTTPException(503, "Address lookup isn't available right now. Drop the pin on the map instead.") from None
