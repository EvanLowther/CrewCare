"""Crew report API: request validation that runs before the database (no database needed)."""

import os

os.environ["PLANIT_MOCK"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from planit.api.main import app  # noqa: E402
from planit.api.reports_store import EXPIRES_AFTER  # noqa: E402
from planit.models import HazardReport  # noqa: E402

client = TestClient(app)


def test_rejects_coordinates_out_of_range():
    r = client.post("/api/reports", data={"latitude": "123", "longitude": "-80.3", "hazard_type": "wildlife",
                                          "severity": "high"})
    assert r.status_code == 422


def test_rejects_unknown_hazard_type():
    r = client.post("/api/reports", data={"latitude": "25.4", "longitude": "-80.3", "hazard_type": "bigfoot",
                                          "severity": "high"})
    assert r.status_code == 422


def test_every_hazard_type_has_an_expiry_rule():
    types = HazardReport.model_fields["hazard_type"].annotation.__args__
    assert set(types) == set(EXPIRES_AFTER)
