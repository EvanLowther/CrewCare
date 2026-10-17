"""Pure-function tests for the NWS ingest (no network, no database)."""

from planit.worker.ingest.nws import (
    affects,
    alert_type_for,
    in_geometry,
    is_relevant,
    severity_for,
    short_message,
    to_rows,
)

SITE = {"id": 6030, "latitude": 47.38, "longitude": -101.16, "nws_zone": "NDZ058", "nws_county_zone": "NDC055"}
SQUARE = {"type": "Polygon", "coordinates": [[[-102, 47], [-100, 47], [-100, 48], [-102, 48], [-102, 47]]]}


def feature(ugc=(), geometry=None):
    return {"geometry": geometry, "properties": {"geocode": {"UGC": list(ugc)}}}


def test_alerts_match_by_polygon_first():
    assert affects(SITE, feature(["NDC001"], SQUARE))  # inside the storm polygon, whatever the county list says
    off = {"type": "Polygon", "coordinates": [[[-99, 47], [-98, 47], [-98, 48], [-99, 48], [-99, 47]]]}
    assert not affects(SITE, feature(["NDC055"], off))  # same county, but the warning polygon misses the site


def test_alerts_match_by_zone_without_polygon():
    assert affects(SITE, feature(["NDZ058"]))
    assert affects(SITE, feature(["NDC055", "NDC057"]))
    assert not affects(SITE, feature(["MNZ001"]))
    assert not affects({**SITE, "nws_zone": None, "nws_county_zone": None}, feature([]))


def test_point_in_multipolygon_with_hole():
    hole = [[-101.5, 47.2], [-100.5, 47.2], [-100.5, 47.6], [-101.5, 47.6], [-101.5, 47.2]]
    donut = {"type": "MultiPolygon", "coordinates": [[SQUARE["coordinates"][0], hole]]}
    assert not in_geometry(-101.16, 47.38, donut)
    assert in_geometry(-101.9, 47.9, donut)


def test_event_types():
    assert alert_type_for("Excessive Heat Warning") == "heat"
    assert alert_type_for("Heat Advisory") == "heat"
    assert alert_type_for("Flash Flood Warning") == "flood"
    assert alert_type_for("Severe Thunderstorm Warning") == "storm"
    assert alert_type_for("Tornado Watch") == "storm"
    assert alert_type_for("Hurricane Warning") == "storm"
    assert alert_type_for("Wind Advisory") == "wind"
    assert alert_type_for("Red Flag Warning") == "wildfire"
    assert alert_type_for("Dense Fog Advisory") == "nws"


def test_severity_comes_from_the_event():
    assert severity_for("Tornado Warning", "Extreme") == "danger"
    assert severity_for("Flash Flood Warning", "Severe") == "danger"
    assert severity_for("Flood Warning", "Severe") == "warning"  # 6.5: restricted work, not stop
    assert severity_for("Wind Advisory", "Moderate") == "warning"
    assert severity_for("Dense Fog Advisory", "Minor") == "info"
    # Unknown events fall back to NWS's severity field
    assert severity_for("Some New Product", "Extreme") == "danger"
    assert severity_for("Some New Product", None) == "info"


def test_relevance_filters_cancels_tests_and_marine():
    assert is_relevant({"status": "Actual", "messageType": "Alert", "event": "Wind Advisory"})
    assert not is_relevant({"status": "Actual", "messageType": "Cancel", "event": "Gale Watch"})
    assert not is_relevant({"status": "Test", "messageType": "Alert", "event": "Tornado Warning"})
    assert not is_relevant({"status": "Actual", "messageType": "Alert", "event": "Small Craft Advisory"})
    assert not is_relevant({"status": "Actual", "messageType": "Alert", "event": "Rip Current Statement"})


def test_short_message_strips_label_and_trims():
    msg = short_message("* WHAT...North winds 20 to 30 mph.\n\n* WHERE...Escambia County.", "Secure loose objects.")
    assert msg == "North winds 20 to 30 mph. Secure loose objects."
    assert len(short_message("word " * 500, None)) <= 400
    assert short_message(None, None) == "See NWS for details."


def test_to_rows():
    feature = {"properties": {
        "id": "urn:oid:2.49.0.1.840.0.abc", "event": "Flood Warning", "severity": "Severe",
        "headline": "Flood Warning for the Suwannee River", "description": "* WHAT...Flooding is occurring.",
        "instruction": None, "onset": "2026-10-17T00:00:00-04:00", "ends": "2026-10-19T12:00:00-04:00",
    }}
    nws_row, app_row = to_rows(638, feature)
    assert nws_row["alert_id"] == app_row["dedupe_key"] == "urn:oid:2.49.0.1.840.0.abc"
    assert app_row["type"] == "flood" and app_row["severity"] == "warning"  # Flood Warning scores 6.5
    assert app_row["message"] == "Flooding is occurring."
    assert app_row["meta"].obj["source"] == "nws"
