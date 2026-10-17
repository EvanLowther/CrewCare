"""Owner: Person B. Who's signed in, their role and their sites (docs/AUTH.md)."""

from fastapi import APIRouter

from planit.api import mock, sites_store
from planit.api.deps import use_mock
from planit.auth import OptionalUser
from planit.models import Me

router = APIRouter(prefix="/api/me", tags=["auth"])


@router.get("", response_model=Me)
def get_me(user: OptionalUser) -> Me:
    """The signed-in user (null when signed out) and the sites they're on."""
    return mock.me(user) if use_mock() else sites_store.me(user)
