"""River flood-risk: hazards.river_flood, the NWPS gauge reader (ingest/river.py) and the alert rows
(rules/flood.py). No network, no database: replies are trimmed copies of real NWPS ones."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from planit import hazards as H
from planit.worker.ingest import river as R
from planit.worker.rules import flood as F

NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)
STAGES = {"action": 30.0, "minor": 35.0, "moderate": 38.0, "major": 40.0}  # Mississippi River at Baton Rouge
BTRL1 = {"lid": "BTRL1", "name": "Mississippi River at Baton Rouge", "usgsId": "", "latitude": 30.4292,
         "longitude": -91.2069,
         "flood": {"categories": {"major": {"stage": 40}, "moderate": {"stage": 38}, "minor": {"stage": 35},
                                  "action": {"stage": 30}}},
         "status": {"observed": {"primary": 12.1, "secondary": 286, "secondaryUnit": "kcfs",
                                 "floodCategory": "no_flooding", "validTime": "2026-10-18T03:00:00Z"}}}
CREEK = {"lid": "ABKL1", "name": "Bayou Manchac at Alligator Bayou", "latitude": 30.3211, "longitude": -91.0208,
         "flood": {"categories": {"major": {"stage": -9999}, "minor": {"stage": -9999}, "action": {"stage": -9999}}}}
BIG_CAJUN = {"id": 6055, "latitude": 30.4300, "longitude": -91.1900}  # ~1 mi from the Baton Rouge gauge
REQ = httpx.Request("GET", "https://api.water.noaa.gov/nwps/v1/gauges/BTRL1")


def test_flood_category_from_the_stage():
    assert H.flood_category(12.1, STAGES) == "no_flooding"
    assert H.flood_category(30.0, STAGES) == "action"
    assert H.flood_category(36.2, STAGES) == "minor"
    assert H.flood_category(41.0, STAGES) == "major"
    assert H.flood_category(None, STAGES) is None
    assert H.flood_category(50.0, {"action": None, "minor": None, "moderate": None, "major": None}) == "no_flooding"


@pytest.mark.parametrize(("category", "severity"), [("action", 5.0), ("minor", 7.5), ("moderate", 9.0),
                                                    ("major", 9.0)])
def test_river_flood_by_the_river_now(category, severity):
    hz = H.river_flood("Mississippi River", 0.0, 36.0, category, None, None, STAGES)
    assert hz.severity == severity and hz.key == "alert_flood"
    assert ("off low ground" in hz.action) == (severity >= 7.5)


def test_river_flood_forecast_and_rain():
    rising = H.river_flood("Mississippi River", 0.0, 33.0, "action", 36.4, "minor", STAGES)
    assert rising.severity == 5.0  # action now; forecast flood stage is also 5
    coming = H.river_flood("Mississippi River", 0.0, 25.0, "no_flooding", 38.5, "moderate", STAGES)
    assert coming.severity == 7.5 and "forecast to reach moderate flood stage (38 ft)" in coming.label
    rain = H.river_flood("Mississippi River", 1.4, 12.0, "no_flooding", 11.8, "no_flooding", STAGES)
    assert rain.severity == 5.0 and rain.label == "1.4 in of rain in 12 h next to the Mississippi River · flood risk"
    assert H.river_flood("Mississippi River", 0.6, 12.0, "no_flooding", 11.8, "no_flooding", STAGES) is None
    assert H.KINDS["alert_flood"] == "water"  # same danger as an NWS Flood Warning: counted once


def test_gauge_stages_names_and_matching():
    assert R.stages(BTRL1) == STAGES and R.has_flood_stages(BTRL1) and not R.has_flood_stages(CREEK)
    assert R.river_name("Mississippi River at Baton Rouge") == "Mississippi River"
    assert R.river_name("Comite River near Comite Joor Rd.") == "Comite River"
    far = {**CREEK, "lid": "FAR", "latitude": 30.60, "longitude": -91.19}  # ~12 mi
    out = {**BTRL1, "lid": "OUT", "status": {"observed": {"floodCategory": "out_of_service"}}}
    near = R.candidates(BIG_CAJUN, [far, CREEK, out, BTRL1], radius_mi=2.0)
    assert [g["lid"] for _, g in near] == ["BTRL1"]  # the creek is 9 mi off, FAR 12 mi, OUT out of service
    row = R.gauge_row(BTRL1)
    assert (row["river"], row["flood"], row["major"], row["usgs_id"]) == ("Mississippi River", 35.0, 40.0, None)


def test_tide_gauges_are_not_rivers():
    assert R.is_river({**BTRL1, "pedts": {"observed": "HGIRG"}})
    assert R.is_river({"name": "Apalachicola River at Woodruff Dam", "pedts": {"observed": "HPIRG"}})  # dam pool
    assert not R.is_river({"name": "Atlantic Ocean Tide Gauge at South Port Everglades",
                           "pedts": {"observed": "HMIRG"}})
    assert not R.is_river({"name": "Tide Gauge at Weedon Island", "pedts": {"observed": "HGIRG"}})  # name backstop
    assert not R.is_river({"name": "Somewhere", "pedts": {}})


def test_requests_back_off_when_nwps_rate_limits(monkeypatch):
    monkeypatch.setattr(R.time, "sleep", lambda s: None)
    replies = iter([httpx.Response(429, request=REQ), httpx.Response(200, json={"ok": 1}, request=REQ)])
    client = type("C", (), {"get": lambda self, url, params=None: next(replies)})()
    assert R._get(client, "/gauges/BTRL1") == {"ok": 1}


def test_latest_observation_and_forecast_peak():
    ts, stage, flow = R.latest_observed(BTRL1)
    assert ts == datetime(2026, 10, 18, 3, tzinfo=UTC) and stage == 12.1 and flow == 286_000
    series = {"data": [{"validTime": (NOW + timedelta(hours=h)).isoformat(), "primary": p}
                       for h, p in [(-6, 50.0), (6, 12.0), (30, 13.5), (47, 13.0), (60, 20.0), (12, -999)]]}
    assert R.forecast_peak(series, NOW) == 13.5  # only the next 48 h, no-data values skipped
    assert R.forecast_peak({"data": []}, NOW) is None


def river_site(**over):
    return {"site_id": 6055, "gauge_id": "BTRL1", "gauge_name": "Mississippi River at Baton Rouge",
            "river": "Mississippi River", "action_stage_ft": 30.0, "flood_stage_ft": 35.0, "moderate_stage_ft": 38.0,
            "major_stage_ft": 40.0, "reading_at": NOW, "stage_ft": 12.1, "forecast_stage_ft": 11.8,
            "category": "no_flooding", **over}


def test_alert_rows_for_rain_and_river():
    assert F.alert_row(river_site(), 0.2, NOW) is None  # calm river, little rain
    rain = F.alert_row(river_site(), 1.3, NOW)
    meta = rain["meta"].obj
    assert rain["type"] == "flood" and rain["dedupe_key"] == "river_flood" and rain["severity"] == "warning"
    assert meta["source"] == "river" and meta["rule_severity"] == 5.0
    assert meta["ends"] == (NOW + timedelta(hours=24)).isoformat()  # rain alone: 24 h after the rain
    flooding = F.alert_row(river_site(stage_ft=36.2, category="minor", forecast_stage_ft=37.0), 0.0, NOW)
    fm = flooding["meta"].obj
    assert flooding["severity"] == "danger" and fm["rule_severity"] == 7.5 and fm["ends"] is None  # until it falls
    assert flooding["title"] == "Flood risk: Mississippi River at 36.2 ft · above flood stage (35 ft)"
    stale = F.alert_row(river_site(stage_ft=None, category=None, forecast_stage_ft=None), 1.5, NOW)
    assert stale["meta"].obj["rule_severity"] == 5.0  # no fresh reading: the rain still counts


def test_a_rain_warning_stays_until_its_24_h_end():
    assert F.still_in_force({"ends": (NOW + timedelta(hours=3)).isoformat()}, NOW)
    assert not F.still_in_force({"ends": (NOW - timedelta(minutes=1)).isoformat()}, NOW)
    assert not F.still_in_force({"ends": None}, NOW)  # a river warning lasts only while the river is up
