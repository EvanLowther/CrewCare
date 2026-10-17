"""Owner: Person B. Who is calling the API (docs/AUTH.md).

The website signs people in with Auth0 and sends their access token as `Authorization: Bearer <token>`. We check
it against Auth0's signing keys, then map the Auth0 user id (`sub`) to a row in `users`, which holds the role.
The first request from a new user creates that row as crew (admin if their verified email is in
PLANIT_ADMIN_EMAILS).

On laptops and in CI, PLANIT_AUTH_DEV=1 also accepts `Authorization: Dev <name>` from the "Sign in as" menu, with
the fake users in DEV_USERS. The server never sets it, so those headers are rejected there.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, Request

from planit.config import admin_email_set, settings
from planit.db import connection

log = logging.getLogger("planit.auth")

# name -> (display name, role). Signed in as "Dev Manager", etc.
DEV_USERS: dict[str, tuple[str, str]] = {
    "admin": ("Dev Admin", "admin"),
    "manager": ("Dev Manager", "manager"),
    "manager2": ("Dev Manager 2", "manager"),
    "crew": ("Dev Crew", "crew"),
    "crew2": ("Dev Crew 2", "crew"),
}
DEV_SUB_PREFIX = "dev|"

_USER_COLS = "id, auth0_sub, email, name, picture, role"


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    sub: str
    email: str | None
    name: str | None
    picture: str | None
    role: str  # admin | manager | crew

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def can_create_sites(self) -> bool:
        return self.role in ("admin", "manager")

    @property
    def display_name(self) -> str | None:
        return self.name or self.email


def _from_row(row: dict) -> CurrentUser:
    return CurrentUser(id=row["id"], sub=row["auth0_sub"], email=row["email"], name=row["name"],
                       picture=row["picture"], role=row["role"])


# --- Auth0 ------------------------------------------------------------------

_jwks: jwt.PyJWKClient | None = None
# sub -> when we last asked Auth0 for an admin-listed user's profile (waiting on email verification).
_ADMIN_RECHECK_SECONDS = 600
_admin_checked: dict[str, float] = {}


def _jwks_client() -> jwt.PyJWKClient:
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(f"https://{settings.auth0_domain}/.well-known/jwks.json", lifespan=3600)
    return _jwks


def verify_token(token: str) -> dict:
    """The token's claims, or 401. Checks the signature, expiry, issuer and that it was issued for our API."""
    if not (settings.auth0_domain and settings.auth0_audience):
        raise HTTPException(401, "Sign-in isn't set up on this server")
    try:
        key = _jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(token, key.key, algorithms=["RS256"], audience=settings.auth0_audience,
                          issuer=f"https://{settings.auth0_domain}/")
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Your sign-in expired or isn't valid. Sign in again.") from exc


def _userinfo(token: str) -> dict:
    """Name, email and email_verified from Auth0 (access tokens don't carry them). Rate limited by Auth0, so it's
    only called for users we haven't seen and for admin-listed emails that aren't admin yet."""
    r = httpx.get(f"https://{settings.auth0_domain}/userinfo", headers={"Authorization": f"Bearer {token}"},
                  timeout=10)
    r.raise_for_status()
    return r.json()


def _save_profile(sub: str, info: dict) -> CurrentUser:
    email = info.get("email")
    is_admin = bool(info.get("email_verified")) and (email or "").lower() in admin_email_set()
    with connection() as conn:
        row = conn.execute(
            f"INSERT INTO users (auth0_sub, email, name, picture, role) VALUES (%s, %s, %s, %s, %s) "
            f"ON CONFLICT (auth0_sub) DO UPDATE SET email = EXCLUDED.email, name = EXCLUDED.name, "
            f"picture = EXCLUDED.picture, last_seen_at = now(), "
            f"role = CASE WHEN %s THEN 'admin' ELSE users.role END "
            f"RETURNING {_USER_COLS}",
            (sub, email, info.get("name") or info.get("nickname"), info.get("picture"),
             "admin" if is_admin else "crew", is_admin),
        ).fetchone()
    return _from_row(row)


def _auth0_user(token: str) -> CurrentUser:
    sub = verify_token(token)["sub"]
    with connection() as conn:
        row = conn.execute(f"UPDATE users SET last_seen_at = now() WHERE auth0_sub = %s RETURNING {_USER_COLS}",
                           (sub,)).fetchone()
    user = _from_row(row) if row else None
    awaiting_admin = (user is not None and user.role != "admin" and (user.email or "").lower() in admin_email_set()
                      and time.monotonic() - _admin_checked.get(sub, -_ADMIN_RECHECK_SECONDS) >= _ADMIN_RECHECK_SECONDS)
    if user is None or awaiting_admin:
        _admin_checked[sub] = time.monotonic()
        try:
            user = _save_profile(sub, _userinfo(token))
        except httpx.HTTPError:
            log.warning("Auth0 /userinfo failed for %s", sub, exc_info=True)
            if user is None:
                raise HTTPException(503, "Couldn't reach the sign-in service. Try again in a moment.") from None
    return user


# --- Dev "Sign in as" -------------------------------------------------------

def _dev_user(name: str) -> CurrentUser:
    if not settings.auth_dev:
        raise HTTPException(401, "Dev sign-in is turned off on this server")
    if name not in DEV_USERS:
        raise HTTPException(401, f"Unknown dev user {name!r}; pick one of {', '.join(DEV_USERS)}")
    display, role = DEV_USERS[name]
    sub, email = f"{DEV_SUB_PREFIX}{name}", f"{name}@dev.planit"
    if settings.mock:  # no database: a fixed id per dev user
        return CurrentUser(id=uuid.uuid5(uuid.NAMESPACE_URL, sub), sub=sub, email=email, name=display,
                           picture=None, role=role)
    with connection() as conn:
        row = conn.execute(
            f"INSERT INTO users (auth0_sub, email, name, role) VALUES (%s, %s, %s, %s) "
            f"ON CONFLICT (auth0_sub) DO UPDATE SET last_seen_at = now(), role = EXCLUDED.role "
            f"RETURNING {_USER_COLS}",
            (sub, email, display, role),
        ).fetchone()
    return _from_row(row)


# --- FastAPI dependencies ---------------------------------------------------

def optional_user(request: Request) -> CurrentUser | None:
    """The signed-in user, or None when the request has no Authorization header (signed out)."""
    scheme, _, credential = request.headers.get("authorization", "").partition(" ")
    credential = credential.strip()
    if not credential:
        return None
    if scheme.lower() == "bearer":
        return _auth0_user(credential)
    if scheme.lower() == "dev":
        return _dev_user(credential)
    raise HTTPException(401, "Unsupported Authorization header")


def require_user(user: Annotated[CurrentUser | None, Depends(optional_user)]) -> CurrentUser:
    if user is None:
        raise HTTPException(401, "Sign in first")
    return user


def require_manager(user: Annotated[CurrentUser, Depends(require_user)]) -> CurrentUser:
    if not user.can_create_sites:
        raise HTTPException(403, "Managers and admins only")
    return user


def require_admin(user: Annotated[CurrentUser, Depends(require_user)]) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(403, "Admins only")
    return user


OptionalUser = Annotated[CurrentUser | None, Depends(optional_user)]
SignedInUser = Annotated[CurrentUser, Depends(require_user)]
ManagerUser = Annotated[CurrentUser, Depends(require_manager)]
AdminUser = Annotated[CurrentUser, Depends(require_admin)]
