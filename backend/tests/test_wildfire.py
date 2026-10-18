"""Pure-function tests for the NIFC wildfire ingest (no network, no database)."""

from datetime import UTC, datetime, timedelta

from planit.worker.ingest.wildfire import alerts_for, fires

NOW = datetime(2026, 10, 17, 18, tzinfo=UTC)
CASTAIC = {"id": 410, "latitude": 34.49, "longitude": -118.62}


def feature(key, name, acres, contained, lon, lat, days_ago=1.0):
    ms = (NOW - timedelta(days=days_ago)).timestamp() * 1000
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"IrwinID": key, "IncidentName": name, "IncidentSize": acres, "PercentContained": contained,
                           "FireDiscoveryDateTime": ms, "UniqueFireIdentifier": f"2026-CA-{key}"}}


FEATURES = [
    feature("{A}", "HUGHES", 10_000, 15, -118.60, 34.55),  # ~4 mi off, ~2 mi across: edge ~2 mi
    feature("{B}", "OLD SPOT", 2, None, -118.61, 34.50, days_ago=10),  # small and stale
    feature("{C}", "CONTAINED", 800, 100, -118.63, 34.51),
    feature("{D}", "FAR AWAY", 50_000, 0, -121.0, 38.0),
    {"type": "Feature", "geometry": None, "properties": {"IrwinID": "{E}", "IncidentName": "NO POINT"}},
]


def test_fires_skip_stale_small_records_and_ones_without_a_point():
    assert [f["id"] for f in fires(FEATURES, NOW)] == ["{A}", "{C}", "{D}"]
    assert fires(FEATURES, NOW)[0]["discovered"] == NOW - timedelta(days=1)


def test_a_close_large_fire_raises_a_scored_wildfire_alert():
    rows = alerts_for([CASTAIC], FEATURES, NOW)[410]
    assert [r["dedupe_key"] for r in rows] == ["{A}"]  # contained and far-away fires raise nothing
    row = rows[0]
    meta = row["meta"].obj
    assert row["type"] == "wildfire" and row["severity"] == "danger"
    assert row["title"].startswith("Hughes Fire 2 mi away, 10,000 acres, 15% contained")
    assert meta["source"] == "nifc" and meta["rule_severity"] >= 7.5 and "Evacuate" in meta["action"]
    assert row["message"].endswith("Source: NIFC.") and row["started_at"] == NOW - timedelta(days=1)


def test_every_site_gets_a_list_so_gone_fires_clear():
    assert alerts_for([CASTAIC, {"id": 1, "latitude": 25.4, "longitude": -80.3}], [], NOW) == {410: [], 1: []}
