"""planit.worker.rules.lightning: alert text, countdown, replay geometry (no network, no database)."""

import random
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from planit.worker import jobs
from planit.worker.rules import lightning as L

LAST = datetime(2026, 10, 17, 18, 42, tzinfo=UTC)  # 2:42 PM in Miami


def agg(**over):
    return {"site_id": 621, "timezone": "America/New_York", "strike_count": 4, "first_strike_at": LAST - timedelta(
        minutes=9), "last_strike_at": LAST, "nearest_mi": 3.24, "latest_mi": 3.24, "latest_bearing": 225.0,
        "source": "replay", **over}


def haversine(lat1, lon1, lat2, lon2):
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * L.EARTH_RADIUS_MI * math.asin(math.sqrt(a))


def test_compass():
    assert [L.compass(b) for b in (0, 22, 23, 90, 225, 337, 359)] == ["N", "N", "NE", "E", "SW", "NW", "N"]
    assert L.compass(None) == ""


def test_alert_fields_countdown_and_text():
    f = L.alert_fields(agg(), all_clear_min=30, radius_mi=10)
    assert f["all_clear_at"] == LAST + timedelta(minutes=30)  # every strike restarts the 30 min
    assert f["title"] == "STOP WORK: lightning within 10 miles"
    assert f["message"] == "Strike 3.2 mi SW at 2:42 PM. All clear at 3:12 PM (30 min) if no new strikes."
    assert f["started_at"] == LAST - timedelta(minutes=9)
    meta = f["meta"].obj
    assert meta["strike_count"] == 4 and meta["nearest_strike_mi"] == 3.2 and meta["latest_bearing"] == "SW"
    assert meta["last_strike_at"] == LAST.isoformat()


def test_alert_fields_use_site_local_time():
    f = L.alert_fields(agg(timezone="America/Los_Angeles"), all_clear_min=30, radius_mi=10)
    assert "at 11:42 AM" in f["message"]


def test_destination_distance():
    lat, lon = L.destination(25.435, -80.331, 90, 5.0)
    assert haversine(25.435, -80.331, lat, lon) == pytest.approx(5.0, abs=0.01)
    assert lon > -80.331 and lat == pytest.approx(25.435, abs=0.01)


def test_replay_points_drift_in_and_stay_inside_the_radius():
    points = L.replay_points(25.435, -80.331, 8, random.Random(3))
    miles = [haversine(25.435, -80.331, lat, lon) for lat, lon in points]
    assert len(points) == 8
    assert all(0.5 <= m <= 10 for m in miles)
    assert miles[-1] < miles[0]  # the cell moves toward the site
    assert L.replay_points(25.435, -80.331, 8, random.Random(3)) == points  # seeded: repeatable


def test_replay_job_is_registered(monkeypatch):
    seen = []
    monkeypatch.setattr(L, "start_replay", seen.append)
    jobs.HANDLERS["lightning_replay"]({"site_id": 621, "strikes": 3, "interval_seconds": 5})
    assert seen[0].site_id == 621 and seen[0].strikes == 3 and seen[0].interval_seconds == 5


class FakeDB:
    """Returns `nearby` for NEARBY_SQL and records the upserts and the clear."""

    def __init__(self, nearby):
        self.nearby, self.calls = nearby, []

    def execute(self, sql, params=None):
        self.calls.append(sql)
        rows = self.nearby if sql == L.NEARBY_SQL else []
        return type("Result", (), {"fetchall": lambda _self: rows})()

    def executemany(self, sql, params):
        self.calls.append(sql)
        self.upserted = list(params)

    @contextmanager
    def transaction(self):
        yield

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @contextmanager
    def connection(self):
        yield self


def test_evaluate_upserts_then_clears(monkeypatch):
    db = FakeDB([agg()])
    monkeypatch.setattr(L, "connection", db.connection)
    assert L.evaluate(now=LAST + timedelta(minutes=1)) == (1, 0)
    assert db.calls == [L.NEARBY_SQL, L.UPSERT_SQL, L.CLEAR_SQL]
    assert db.upserted[0]["site_id"] == 621


def test_evaluate_with_no_lightning_only_clears(monkeypatch):
    db = FakeDB([])
    monkeypatch.setattr(L, "connection", db.connection)
    L.evaluate(now=LAST)
    assert db.calls == [L.NEARBY_SQL, L.CLEAR_SQL]
