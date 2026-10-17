"""Owner: Person B. Dashboard and site page data."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from planit.api import mock
from planit.api.deps import not_built, use_mock
from planit.models import SiteDetail, SiteList

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.get("", response_model=SiteList)
def list_sites() -> SiteList:
    """All sites, highest risk first."""
    if use_mock():
        return SiteList(sites=mock.site_summaries(), updated_at=datetime.now(UTC))
    # TODO (hours 1-4): sites + latest hazard_scores + active alert counts + latest heat index
    raise not_built("GET /api/sites")


@router.get("/{site_id}", response_model=SiteDetail)
def get_site(site_id: int) -> SiteDetail:
    if use_mock():
        detail = mock.site_detail(site_id)
        if detail is None:
            raise HTTPException(404, "Site not found")
        return detail
    # TODO (hours 1-4)
    raise not_built("GET /api/sites/{id}")
