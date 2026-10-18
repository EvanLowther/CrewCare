"""api/sites_store.py: creating or moving a site queues the worker's 'site_setup' job (fake connection, no DB)."""

from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from uuid import uuid4

from planit.api import sites_store
from planit.models import SiteCreate, SiteUpdate


class FakeConn:
    def __init__(self):
        self.sql: list[tuple[str, object]] = []

    def transaction(self):
        return nullcontext()

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), params))
        row = {"id": 9000001, "latitude": 34.0, "longitude": -118.0}
        return SimpleNamespace(fetchone=lambda: row, fetchall=lambda: [row])


def patch(monkeypatch) -> FakeConn:
    conn = FakeConn()

    @contextmanager
    def connection():
        yield conn
    monkeypatch.setattr(sites_store, "connection", connection)
    monkeypatch.setattr(sites_store, "_place", lambda lat, lon: {"lat": lat, "lon": lon, "state": "CA",
                                                                  "timezone": "America/Los_Angeles"})
    monkeypatch.setattr(sites_store, "_require_manage", lambda conn, site_id, user: {})
    return conn


def setup_jobs(conn: FakeConn) -> list:
    return [p[0].obj for sql, p in conn.sql if "INSERT INTO job_requests" in sql and "site_setup" in sql]


USER = SimpleNamespace(id=uuid4())


def test_a_new_site_queues_its_setup(monkeypatch):
    conn = patch(monkeypatch)
    sites_store.create_site(SiteCreate(name="Yard 7", latitude=34.5, longitude=-118.6), USER)
    assert setup_jobs(conn) == [{"site_id": 9000001}]


def test_moving_a_site_drops_the_old_weather_and_queues_setup(monkeypatch):
    conn = patch(monkeypatch)
    sites_store.update_site(9000001, SiteUpdate(latitude=35.0, longitude=-119.0), USER)
    deleted = [sql for sql, _ in conn.sql if sql.startswith("DELETE FROM")]
    assert deleted == ["DELETE FROM weather WHERE site_id = %s", "DELETE FROM nws_weather WHERE site_id = %s",
                       "DELETE FROM air_quality WHERE site_id = %s"]
    assert setup_jobs(conn) == [{"site_id": 9000001}]


def test_renaming_a_site_queues_nothing(monkeypatch):
    conn = patch(monkeypatch)
    sites_store.update_site(9000001, SiteUpdate(name="Yard 7B"), USER)
    assert setup_jobs(conn) == [] and not any(sql.startswith("DELETE") for sql, _ in conn.sql)
