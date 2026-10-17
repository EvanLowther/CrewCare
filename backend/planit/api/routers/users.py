"""Owner: Person B. Finding people to add to a site."""

from fastapi import APIRouter, Query

from planit.api import sites_store
from planit.api.deps import not_built, use_mock
from planit.auth import ManagerUser
from planit.models import UserList

router = APIRouter(prefix="/api/users", tags=["auth"])


@router.get("", response_model=UserList)
def search_users(user: ManagerUser, q: str = Query(min_length=2, max_length=100)) -> UserList:
    """Signed-up users whose name or email contains `q`. Managers and admins only."""
    if use_mock():
        raise not_built("GET /api/users")
    return UserList(users=sites_store.search_users(q))
