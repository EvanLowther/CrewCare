"""Who may see and do what (planit/api/access.py): the rules, without a database."""

import time
import uuid

from planit.api import access
from planit.auth import CurrentUser


def user(role: str) -> CurrentUser:
    return CurrentUser(id=uuid.uuid4(), sub=f"test|{role}", email=f"{role}@x.com", name=role, picture=None, role=role)


ADMIN, MANAGER, CREW = user("admin"), user("manager"), user("crew")
SITE = (25.435, -80.331)  # Turkey Point


def test_reference_sites_are_public_private_sites_are_members_only():
    assert access.can_view(None, is_reference=True, my_role=None)
    assert not access.can_view(None, is_reference=False, my_role=None)
    assert not access.can_view(CREW, is_reference=False, my_role=None)
    assert access.can_view(CREW, is_reference=False, my_role="crew")
    assert access.can_view(ADMIN, is_reference=False, my_role=None)


def test_visibility_sql_by_viewer():
    assert access.visible_sites_sql(None) == ("s.is_reference", {})
    assert access.visible_sites_sql(ADMIN) == ("TRUE", {})
    sql, params = access.visible_sites_sql(CREW)
    assert "site_members" in sql and params == {"viewer_id": CREW.id}


def test_site_managers_and_admins_manage():
    assert access.can_manage(MANAGER, "manager")
    assert not access.can_manage(MANAGER, "crew")
    assert not access.can_manage(CREW, "crew")
    assert access.can_manage(ADMIN, None)
    assert not access.can_manage(None, None)


def test_only_the_creating_manager_or_an_admin_deletes():
    assert access.can_delete(MANAGER, "manager", MANAGER.id)
    assert not access.can_delete(MANAGER, "manager", uuid.uuid4())
    assert not access.can_delete(MANAGER, None, MANAGER.id)  # no longer on the site
    assert access.can_delete(ADMIN, None, uuid.uuid4())


def test_members_report_admins_anywhere():
    assert access.can_report(CREW, "crew") and access.can_report(MANAGER, "manager")
    assert not access.can_report(CREW, None)
    assert access.can_report(ADMIN, None)
    assert not access.can_report(None, None)


def test_crew_cannot_be_site_managers():
    assert access.member_role_error("crew", "manager")
    assert access.member_role_error("crew", "crew") is None
    assert access.member_role_error("manager", "manager") is None


def test_miles_between():
    assert access.miles_between(*SITE, *SITE) == 0
    # One degree of latitude is about 69 miles.
    assert 68.5 < access.miles_between(25.0, -80.0, 26.0, -80.0) < 69.5


def test_report_needs_gps_and_pin_within_five_miles():
    near = (25.47, -80.33)  # ~2.4 mi north
    far = (25.55, -80.33)  # ~8 mi north
    assert access.report_location_error(*SITE, "Turkey Point", pin=near, gps=near) is None
    assert "Turn on location" in access.report_location_error(*SITE, "Turkey Point", pin=near, gps=None)
    assert "7.9 mi away" in access.report_location_error(*SITE, "Turkey Point", pin=near, gps=far)
    assert "pin" in access.report_location_error(*SITE, "Turkey Point", pin=far, gps=near)


def test_photo_links_are_signed_and_expire():
    pid, now = uuid.uuid4(), time.time()
    url = access.signed_photo_url(pid, now)
    params = dict(p.split("=") for p in url.split("?")[1].split("&"))
    exp, sig = int(params["exp"]), params["sig"]
    assert access.photo_signature_ok(pid, exp, sig, now)
    assert not access.photo_signature_ok(uuid.uuid4(), exp, sig, now)  # another photo
    assert not access.photo_signature_ok(pid, exp, "0" * 32, now)  # forged
    assert not access.photo_signature_ok(pid, exp, sig, exp + 1)  # expired
