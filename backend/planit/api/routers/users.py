"""Owner: Person B. Finding people to add to a site, and addresses to place one."""

from fastapi import APIRouter, Query

from planit.api import geocode, sites_store
from planit.api.deps import not_built, use_mock
from planit.auth import ManagerUser
from planit.models import GeocodeList, UserList

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/users", response_model=UserList)
def search_users(user: ManagerUser, q: str = Query(min_length=2, max_length=100)) -> UserList:
    """Signed-up users whose name or email contains `q`. Managers and admins only."""
    if use_mock():
        raise not_built("GET /api/users")
    return UserList(users=sites_store.search_users(q))


@router.get("/geocode", response_model=GeocodeList, tags=["sites"])
def geocode_address(user: ManagerUser, q: str = Query(min_length=3, max_length=200)) -> GeocodeList:
    """US addresses or places matching `q`, best first, for placing a new site. Managers and admins only."""
    if use_mock():
        raise not_built("GET /api/geocode")
    return GeocodeList(results=geocode.search(q))
