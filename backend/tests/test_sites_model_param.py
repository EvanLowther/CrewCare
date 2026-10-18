"""The `model` switch on /api/sites (mock mode, no database)."""

import os

os.environ["PLANIT_MOCK"] = "1"

from fastapi.testclient import TestClient

from planit.api.main import app

client = TestClient(app)


def test_model_param_accepts_ml_and_rules():
    for model in ("ml", "rules"):
        assert client.get(f"/api/sites?model={model}").status_code == 200
        first = client.get(f"/api/sites?model={model}").json()["sites"][0]
        assert client.get(f"/api/sites/{first['id']}?model={model}").status_code == 200


def test_model_param_rejects_unknown_scorers():
    assert client.get("/api/sites?model=random-forest").status_code == 422


def test_hours_ahead_is_0_to_24():
    for hours in (0, 6, 24):
        assert client.get(f"/api/sites?hours_ahead={hours}").status_code == 200
    for hours in (-1, 25):
        assert client.get(f"/api/sites?hours_ahead={hours}").status_code == 422
