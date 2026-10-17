"""Every mock endpoint returns data that matches the contract in planit/models.py."""

import os

os.environ["PLANIT_MOCK"] = "1"

from fastapi.testclient import TestClient

from planit.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["mock"] is True


def test_sites_sorted_by_risk():
    sites = client.get("/api/sites").json()["sites"]
    assert len(sites) >= 10
    scores = [s["risk"]["score"] for s in sites]
    assert scores == sorted(scores, reverse=True)


def test_site_detail():
    first = client.get("/api/sites").json()["sites"][0]
    detail = client.get(f"/api/sites/{first['id']}").json()
    assert detail["site"]["id"] == first["id"]
    assert len(detail["forecast"]) == 48
    assert client.get("/api/sites/1").status_code == 404


def test_alerts_have_lightning_countdown():
    alerts = client.get("/api/alerts").json()["alerts"]
    lightning = [a for a in alerts if a["type"] == "lightning"]
    assert lightning and lightning[0]["all_clear_at"]


def test_briefings_and_reports():
    assert client.get("/api/briefings").json()["briefings"]
    assert client.get("/api/reports").json()["reports"]
