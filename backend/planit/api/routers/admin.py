"""Owner: Person B. Admin page: everyone who signed up, and their roles."""

from uuid import UUID

from fastapi import APIRouter

from planit.api import sites_store
from planit.api.deps import not_built, use_mock
from planit.auth import AdminUser as Admin
from planit.models import AdminUser, AdminUserList, RoleUpdate

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=AdminUserList)
def list_users(admin: Admin) -> AdminUserList:
    if use_mock():
        raise not_built("GET /api/admin/users")
    return AdminUserList(users=sites_store.list_users())


@router.patch("/users/{user_id}", response_model=AdminUser)
def set_role(user_id: UUID, req: RoleUpdate, admin: Admin) -> AdminUser:
    """Make someone admin, manager or crew. Demoting a manager to crew makes them crew on their sites too."""
    if use_mock():
        raise not_built("PATCH /api/admin/users/{id}")
    return sites_store.set_role(user_id, req.role, admin)
