"""Notifications, the live stream, push and past hazards at the API edge (mock mode, no database)."""

import json
import os

os.environ["PLANIT_MOCK"] = "1"
os.environ["PLANIT_AUTH_DEV"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from planit.api import push  # noqa: E402
from planit.api.main import app  # noqa: E402
from planit.api.routers import notifications  # noqa: E402

client = TestClient(app)
CREW = {"Authorization": "Dev crew"}
MANAGER = {"Authorization": "Dev manager"}


def test_notifications_need_sign_in():
    assert client.get("/api/notifications").status_code == 401
    assert client.get("/api/notifications/stream").status_code == 401


def test_notifications_list_newest_first_with_unread_count():
    body = client.get("/api/notifications", headers=CREW).json()
    ids = [n["id"] for n in body["notifications"]]
    assert ids == sorted(ids, reverse=True)
    assert body["unread"] == sum(not n["read"] for n in body["notifications"])
    assert {n["kind"] for n in body["notifications"]} == {"crew_report", "alert", "briefing"}


def test_stream_says_ready_first(monkeypatch):
    monkeypatch.setattr(notifications, "STREAM_SECONDS", 0.1)  # the test client waits for the stream to end
    with client.stream("GET", "/api/notifications/stream?after=7", headers=CREW) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        lines = r.iter_lines()
        assert next(lines) == "event: ready"
        data = next(lines)
        assert json.loads(data.removeprefix("data: ")) == {"after": 7}


def test_push_key_is_null_without_vapid_keys():
    assert client.get("/api/notifications/push-key").json() == {"public_key": None}
    assert not push.enabled()


def test_push_payload_is_what_the_service_worker_reads():
    payload = json.loads(push._payload({"id": 5, "title": "Tornado Warning · Barry", "body": None,
                                        "link": "/sites/3", "kind": "alert", "severity": "danger"}))
    assert payload == {"id": 5, "title": "Tornado Warning · Barry", "body": "", "url": "/sites/3", "kind": "alert",
                       "severity": "danger"}


def test_subscribe_validates_the_browser_subscription():
    ok = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}
    assert client.post("/api/notifications/subscriptions", json=ok, headers=CREW).status_code == 204
    assert client.post("/api/notifications/subscriptions", json={"endpoint": "x"}, headers=CREW).status_code == 422


def test_site_history_is_public_but_place_history_is_for_managers():
    site = client.get("/api/sites/9001/history").json()
    assert site["report_radius_mi"] == 5 and site["storm_radius_mi"] == 25
    assert site["storm_event_count"] >= len(site["storm_events"])
    assert client.get("/api/history?lat=27&lon=-82", headers=CREW).status_code == 403
    assert client.get("/api/history?lat=27&lon=-82", headers=MANAGER).status_code == 200
    assert client.get("/api/history?lat=127&lon=-82", headers=MANAGER).status_code == 422
