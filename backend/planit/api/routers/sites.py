"""Owner: Person B. Dashboard and site page data; managers create sites and choose who's on them."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response

from planit.api import mock, queries, sites_store
from planit.api.deps import not_built, use_mock
from planit.auth import ManagerUser, OptionalUser, SignedInUser
from planit.models import MemberAdd, SiteCreate, SiteDetail, SiteList, SiteMemberList, SiteUpdate

router = APIRouter(prefix="/api/sites", tags=["sites"])

Scorer = Literal["ml", "rules"]
MODEL_QUERY = Query(None, description="Whose risk scores: 'ml' (XGBoost, Predictive) or 'rules' (rules-v2, "
                          "Real-time). Default: ml.")


HOURS_AHEAD_QUERY = Query(0, ge=0, le=24, description="Score each site with its forecast this many hours from now "
                          "(the dashboard's time slider). 0: the current score.")


@router.get("", response_model=SiteList)
def list_sites(user: OptionalUser, model: Scorer | None = MODEL_QUERY,
               hours_ahead: int = HOURS_AHEAD_QUERY) -> SiteList:
    """Sites the viewer may see (reference sites, plus their own; admins see all), highest risk first."""
    if use_mock():
        return SiteList(sites=mock.site_summaries(), updated_at=datetime.now(UTC))
    return SiteList(sites=queries.list_sites(model, user, hours_ahead), updated_at=datetime.now(UTC))


@router.get("/{site_id}", response_model=SiteDetail)
def get_site(site_id: int, user: OptionalUser, model: Scorer | None = MODEL_QUERY) -> SiteDetail:
    try:
        detail = mock.site_detail(site_id) if use_mock() else queries.get_site(site_id, model, user)
    except queries.SiteHidden:
        raise HTTPException(403, "You're not on this site") from None
    if detail is None:
        raise HTTPException(404, "Site not found")
    return detail


@router.post("", response_model=SiteDetail, status_code=201)
def create_site(req: SiteCreate, user: ManagerUser) -> SiteDetail:
    """A new private site; the creator becomes its manager. Managers and admins only."""
    if use_mock():
        raise not_built("POST /api/sites")
    site_id = sites_store.create_site(req, user)
    return queries.get_site(site_id, None, user)


@router.patch("/{site_id}", response_model=SiteDetail)
def update_site(site_id: int, req: SiteUpdate, user: SignedInUser) -> SiteDetail:
    """Rename, move or re-describe a site. Its managers and admins only."""
    if use_mock():
        raise not_built("PATCH /api/sites/{id}")
    sites_store.update_site(site_id, req, user)
    return queries.get_site(site_id, None, user)


@router.delete("/{site_id}", status_code=204)
def delete_site(site_id: int, user: SignedInUser) -> Response:
    """Deletes the site and its history. The manager who created it, or an admin."""
    if use_mock():
        raise not_built("DELETE /api/sites/{id}")
    sites_store.delete_site(site_id, user)
    return Response(status_code=204)


@router.get("/{site_id}/members", response_model=SiteMemberList)
def list_members(site_id: int, user: SignedInUser) -> SiteMemberList:
    """Who's on the site. Its members and admins."""
    if use_mock():
        raise not_built("GET /api/sites/{id}/members")
    return SiteMemberList(members=sites_store.list_members(site_id, user))


@router.post("/{site_id}/members", response_model=SiteMemberList)
def add_member(site_id: int, req: MemberAdd, user: SignedInUser) -> SiteMemberList:
    """Add someone (or change their role on the site). Only users with the manager role can be site managers."""
    if use_mock():
        raise not_built("POST /api/sites/{id}/members")
    return SiteMemberList(members=sites_store.add_member(site_id, req.user_id, req.role, user))


@router.delete("/{site_id}/members/{user_id}", response_model=SiteMemberList)
def remove_member(site_id: int, user_id: UUID, user: SignedInUser) -> SiteMemberList:
    if use_mock():
        raise not_built("DELETE /api/sites/{id}/members/{user_id}")
    return SiteMemberList(members=sites_store.remove_member(site_id, user_id, user))
