"""Sign-in at the API edge (mock mode, no database): dev users, required roles, and the demo buttons."""

import os

os.environ["PLANIT_MOCK"] = "1"
os.environ["PLANIT_AUTH_DEV"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from planit.api.main import app  # noqa: E402
from planit.config import settings  # noqa: E402

client = TestClient(app)


def as_(name: str) -> dict:
    return {"Authorization": f"Dev {name}"}


def test_signed_out_me_is_null():
    r = client.get("/api/me")
    assert r.status_code == 200 and r.json()["user"] is None


def test_dev_users_have_roles_and_sites():
    me = client.get("/api/me", headers=as_("manager")).json()
    assert me["user"]["role"] == "manager" and me["auth"] == "dev"
    assert {"manager", "crew"} >= {s["role"] for s in me["sites"]}
    assert client.get("/api/me", headers=as_("crew")).json()["user"]["role"] == "crew"


def test_unknown_dev_user_and_bad_tokens_are_rejected():
    assert client.get("/api/me", headers=as_("root")).status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Basic abc"}).status_code == 401
    # No Auth0 settings in tests, so any bearer token is refused.
    assert client.get("/api/me", headers={"Authorization": "Bearer abc.def.ghi"}).status_code == 401


def test_dev_sign_in_is_refused_when_turned_off(monkeypatch):
    monkeypatch.setattr(settings, "auth_dev", False)
    assert client.get("/api/me", headers=as_("admin")).status_code == 401


def test_writes_need_a_signed_in_user():
    assert client.post("/api/sites", json={"name": "New", "latitude": 28, "longitude": -82}).status_code == 401
    form = {"site_id": "9001", "latitude": "25.4", "longitude": "-80.3", "hazard_type": "wildlife",
            "severity": "high"}
    assert client.post("/api/reports", data=form).status_code == 401


def test_only_managers_create_sites():
    body = {"name": "New site", "latitude": 28, "longitude": -82}
    assert client.post("/api/sites", json=body, headers=as_("crew")).status_code == 403


def test_demo_buttons_are_admin_only():
    replay = {"site_id": 9001}
    assert client.post("/api/demo/lightning-replay", json=replay, headers=as_("manager")).status_code == 403
    assert client.post("/api/demo/lightning-replay", json=replay, headers=as_("admin")).status_code == 200
    assert client.post("/api/briefings/generate", headers=as_("crew")).status_code == 403


def test_admin_pages_are_admin_only():
    assert client.get("/api/admin/users", headers=as_("manager")).status_code == 403
    assert client.get("/api/users?q=ab", headers=as_("crew")).status_code == 403
    assert client.get("/api/geocode?q=Gainesville", headers=as_("crew")).status_code == 403
