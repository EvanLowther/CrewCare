"""Pure-function tests for the NWS ingest (no network, no database)."""

from planit.worker.ingest.nws import alert_type_for, is_relevant, severity_for, short_message, to_rows


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


def test_severity():
    assert severity_for("Extreme") == "danger"
    assert severity_for("Severe") == "danger"
    assert severity_for("Moderate") == "warning"
    assert severity_for("Minor") == "info"
    assert severity_for(None) == "info"


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
    assert app_row["type"] == "flood" and app_row["severity"] == "danger"
    assert app_row["message"] == "Flooding is occurring."
    assert app_row["meta"].obj["source"] == "nws"
