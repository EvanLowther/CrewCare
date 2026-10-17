"""Owner: Person B. Dashboard and site page data."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from planit.api import mock, queries
from planit.api.deps import use_mock
from planit.models import SiteDetail, SiteList

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.get("", response_model=SiteList)
def list_sites() -> SiteList:
    """All sites, highest risk first."""
    if use_mock():
        return SiteList(sites=mock.site_summaries(), updated_at=datetime.now(UTC))
    return SiteList(sites=queries.list_sites(), updated_at=datetime.now(UTC))


@router.get("/{site_id}", response_model=SiteDetail)
def get_site(site_id: int) -> SiteDetail:
    detail = mock.site_detail(site_id) if use_mock() else queries.get_site(site_id)
    if detail is None:
        raise HTTPException(404, "Site not found")
    return detail
