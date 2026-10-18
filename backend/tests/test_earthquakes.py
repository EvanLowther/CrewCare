"""Pure-function tests for the USGS earthquake ingest (no network, no database)."""

from datetime import UTC, datetime, timedelta

from planit.worker.ingest.earthquakes import QUAKE_ALERT_HOURS, alert_row, alerts_for, quakes

NOW = datetime(2026, 10, 17, 18, tzinfo=UTC)
CASTAIC = {"id": 410, "latitude": 34.49, "longitude": -118.62}
FAR = {"id": 6030, "latitude": 47.38, "longitude": -101.16}


def feature(event_id, mag, lon, lat, depth, hours_ago=1.0, kind="earthquake"):
    ms = (NOW - timedelta(hours=hours_ago)).timestamp() * 1000
    return {"type": "Feature", "id": event_id, "geometry": {"type": "Point", "coordinates": [lon, lat, depth]},
            "properties": {"mag": mag, "place": "6 km N of Castaic, CA", "time": ms, "type": kind,
                           "url": f"https://earthquake.usgs.gov/earthquakes/eventpage/{event_id}"}}


FEED = {"features": [
    feature("ci1", 6.0, -118.62, 34.55, 8.0),  # ~4 mi from Castaic
    feature("ci2", 2.6, -116.0, 33.0, 5.0),  # small and far
    feature("ci3", 3.1, -118.60, 34.50, 0.1, kind="quarry blast"),
    feature("ci4", 5.5, -118.62, 34.52, 10.0, hours_ago=QUAKE_ALERT_HOURS + 1),  # past its alert window
    {"type": "Feature", "id": "ci5", "geometry": None, "properties": {"mag": None, "type": "earthquake", "time": 0}},
]}


def test_quakes_keep_earthquakes_with_a_magnitude_and_location():
    assert [q["id"] for q in quakes(FEED)] == ["ci1", "ci2", "ci4"]
    q = quakes(FEED)[0]
    assert q["magnitude"] == 6.0 and q["depth_km"] == 8.0 and q["time"] == NOW - timedelta(hours=1)


def test_a_nearby_m6_raises_an_earthquake_alert_scored_by_the_rules():
    row = alert_row(CASTAIC, quakes(FEED)[0])
    meta = row.pop("meta").obj
    assert row["type"] == "earthquake" and row["dedupe_key"] == "ci1" and row["severity"] == "warning"
    assert row["title"] == "M6.0 earthquake 4 mi away · shaking VI (est.)"
    assert "Estimated shaking at the site: VI" in row["message"]
    assert 6.0 < meta["mmi"] < 6.5 and 5 < meta["rule_severity"] < 6.5 and meta["source"] == "usgs"
    assert meta["ends"] == (NOW - timedelta(hours=1) + timedelta(hours=QUAKE_ALERT_HOURS)).isoformat()


def test_far_or_small_quakes_and_old_ones_raise_nothing():
    per_site = alerts_for([CASTAIC, FAR], FEED, NOW)
    assert [r["dedupe_key"] for r in per_site[410]] == ["ci1"]  # ci4 is past its window
    assert per_site[6030] == []  # every site gets a list, so its old alerts can be cleared
