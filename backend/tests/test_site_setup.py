"""worker/site_setup.py: a new or moved site gets its weather and scores at once (no network, no database)."""

from contextlib import contextmanager

from planit.worker import jobs, site_setup


class FakeConn:
    def __init__(self, exists: bool):
        self.exists = exists

    def execute(self, sql, params=None):
        return type("Cursor", (), {"fetchone": lambda _self: {"?column?": 1} if self.exists else None})()


def fake_connection(exists: bool):
    @contextmanager
    def connection():
        yield FakeConn(exists)
    return connection


def record(monkeypatch, exists=True):
    calls = []
    monkeypatch.setattr(site_setup, "connection", fake_connection(exists))
    monkeypatch.setattr(site_setup.nws_weather, "poll", lambda **kw: calls.append(("nws_weather", kw)))
    monkeypatch.setattr(site_setup.open_meteo, "poll", lambda **kw: calls.append(("open_meteo", kw)))
    monkeypatch.setattr(site_setup.air_quality, "poll", lambda **kw: calls.append(("air_quality", kw)))
    monkeypatch.setattr(site_setup.river, "poll", lambda **kw: calls.append(("river", kw)))
    monkeypatch.setattr(site_setup.flood, "evaluate", lambda: calls.append(("flood", {})))
    monkeypatch.setattr(site_setup.nws, "poll", lambda: calls.append(("nws", {})))
    monkeypatch.setattr(site_setup.wildfire, "poll", lambda: calls.append(("wildfire", {})))

    def quakes_down():
        raise RuntimeError("USGS down")
    monkeypatch.setattr(site_setup.earthquakes, "poll", quakes_down)
    monkeypatch.setattr(site_setup.score, "score_all", lambda: calls.append(("score", {})))
    return calls


def test_setup_fetches_only_that_site_with_rain_history_then_scores(monkeypatch):
    calls = record(monkeypatch)
    assert jobs.HANDLERS["site_setup"]({"site_id": 9000001}) is not False
    assert calls[:4] == [("nws_weather", {"site_ids": [9000001]}),
                         ("open_meteo", {"site_ids": [9000001], "past_days": site_setup.SETUP_PAST_DAYS}),
                         ("air_quality", {"site_ids": [9000001]}),
                         ("river", {"site_ids": [9000001]})]  # its nearest flood-staged river gauge
    # Alerts for its location (river flood risk too), and the scores even though the quake feed failed.
    assert [name for name, _ in calls[4:]] == ["nws", "wildfire", "flood", "score"]
    assert site_setup.SETUP_PAST_DAYS >= 4  # the model's 12 h window + 3 days of rain before it


def test_setup_skips_a_site_deleted_before_the_job_ran(monkeypatch):
    calls = record(monkeypatch, exists=False)
    assert site_setup.run(9000001) is False and calls == []
