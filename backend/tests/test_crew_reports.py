"""Crew reports in the risk picture: hazards.crew_report, data confirmation, the scores, the alerts and the confirm
route (no network, no database)."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

os.environ["PLANIT_MOCK"] = "1"
os.environ["PLANIT_AUTH_DEV"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from planit import hazards as H  # noqa: E402
from planit.api.main import app  # noqa: E402
from planit.api.mock import _FIXED_IDS  # noqa: E402
from planit.ml import score as S  # noqa: E402
from planit.worker.rules import crew_reports as C  # noqa: E402

T0 = datetime(2026, 10, 18, 15, tzinfo=UTC)


def report(hazard_type="wildlife", severity="medium", minutes_ago=30, expires_in_h=24, **over):
    return {"id": uuid4(), "hazard_type": hazard_type, "severity": severity,
            "created_at": T0 - timedelta(minutes=minutes_ago),
            "expires_at": T0 + timedelta(hours=expires_in_h) if expires_in_h is not None else None,
            "confirmed_at": None, "confirmed_by_name": None, **over}


# --- hazards.crew_report ------------------------------------------------------------------------------------

def test_severity_by_type_and_rating():
    assert H.crew_report("downed_line", "high").severity == 8.5  # can reach extreme
    assert H.crew_report("fire", "high").severity == 8.5
    assert H.crew_report("wildlife", "low").severity == 2.5 and H.crew_report("wildlife", "high").severity == 6.0
    assert H.crew_report("gas_leak", "high").severity == 7.0  # high at most, unless a manager confirms
    assert H.crew_report("other", "medium").severity == 4.5  # the default row


def test_checkable_reports_count_at_most_moderate_until_confirmed():
    unconfirmed = H.crew_report("high_wind", "high")
    assert unconfirmed.severity == H.CREW_UNCONFIRMED_CAP and unconfirmed.label.endswith("· not yet confirmed")
    by_data = H.crew_report("high_wind", "high", confirmed_by="gusts 31 mph")
    assert by_data.severity == 6.5 and by_data.label == "Crew report: high wind (high) · confirmed by gusts 31 mph"
    wildlife = H.crew_report("wildlife", "high")  # no feed can see a gator: counts as reported
    assert wildlife.severity == 6.0 and "confirmed" not in wildlife.label


def test_a_manager_confirmation_lifts_the_cap():
    confirmed = H.crew_report("wildlife", "high", count=3, confirmed_by="J. Ramirez", by_manager=True)
    assert confirmed.severity == H.CREW_CONFIRMED_HIGH  # a confirmed high of any type can be extreme
    assert confirmed.label == "Crew report: wildlife (high) · 3 reports · confirmed by J. Ramirez"
    assert H.crew_report("smoke", "medium", confirmed_by="J. Ramirez", by_manager=True).severity == 4.5


def test_reports_share_a_kind_with_the_weather_they_describe():
    assert H.KINDS["report_flooding"] == H.KINDS["rain_24h"] == "water"
    assert H.KINDS["report_lightning"] == H.KINDS["lightning"] == "storm"
    assert "report_wildlife" not in H.KINDS  # its own kind
    rain, flooding = H.rain_24h(3.0), H.crew_report("flooding", "high", confirmed_by="3.0 in of rain in 24 h")
    assert H.combine([rain, flooding])[0] == max(rain.severity, flooding.severity)  # one water danger


# --- confirmation by data -----------------------------------------------------------------------------------

@pytest.mark.parametrize(("hazard_type", "x", "source"), [
    ("lightning", S.HourInputs(alerts=[{"type": "lightning"}]), "GOES lightning"),
    ("high_wind", S.HourInputs(gust_mph=31.0), "gusts 31 mph"),
    ("high_wind", S.HourInputs(alerts=[{"type": "wind"}]), "an NWS wind alert"),
    ("flooding", S.HourInputs(rain_24h_in=0.8), "0.8 in of rain in 24 h"),
    ("flooding", S.HourInputs(alerts=[{"type": "flood"}]), "a flood alert"),
    ("ice", S.HourInputs(temp_f=31.0, rain_24h_in=0.1), "31°F with precipitation"),
    ("snow", S.HourInputs(alerts=[{"type": "nws", "nws_event": "Winter Storm Warning"}]), "an NWS winter alert"),
    ("smoke", S.HourInputs(us_aqi_pm2_5=160.0), "AQI 160"),
    ("heat_illness", S.HourInputs(heat_index_f=97.0), "heat index 97°F"),
    ("cold_stress", S.HourInputs(wind_chill_f=24.0), "wind chill 24°F"),
])
def test_live_data_confirms(hazard_type, x, source):
    assert S.report_confirmation(hazard_type, x) == source


@pytest.mark.parametrize(("hazard_type", "x"), [
    ("lightning", S.HourInputs()),
    ("high_wind", S.HourInputs(gust_mph=18.0)),
    ("flooding", S.HourInputs(rain_24h_in=0.1)),
    ("ice", S.HourInputs(temp_f=31.0, rain_24h_in=0.0, snow_24h_in=0.0)),  # cold but dry
    ("smoke", S.HourInputs(us_aqi_pm2_5=60.0)),
    ("heat_illness", S.HourInputs(heat_index_f=80.0)),
    ("wildlife", S.HourInputs(gust_mph=50.0)),  # nothing to check
])
def test_live_data_never_rejects_it_only_fails_to_confirm(hazard_type, x):
    assert S.report_confirmation(hazard_type, x) is None


# --- in the scores ------------------------------------------------------------------------------------------

def test_reports_count_while_active_and_once_per_type():
    reports = [report("wildlife", "low"), report("wildlife", "high"), report("wildlife", "medium"),
               report("downed_line", "low", minutes_ago=600, expires_in_h=-1)]  # expired an hour ago
    x = S.HourInputs(reports=S.reports_at(reports, T0))
    hazards = S.crew_hazards(x)
    assert len(hazards) == 1  # the expired downed line is gone
    assert hazards[0].label == "Crew report: wildlife (high) · 3 reports" and hazards[0].severity == 6.0
    later = S.reports_at([report("fire", minutes_ago=-90)], T0)  # filed after this hour ends
    assert later == []


def test_a_report_sets_the_real_time_score_with_its_action():
    x = S.HourInputs(gust_mph=8.0, reports=S.reports_at([report("downed_line", "high")], T0))
    score, factors = S.score_hour(x)
    assert score == 8.5 and S.level_for(score) == "extreme"
    assert factors[0]["key"] == "report_downed_line" and "35 ft" in factors[0]["action"]


def test_a_manager_confirmed_report_counts_fully():
    gusty = report("high_wind", "high", confirmed_at=T0, confirmed_by_name="J. Ramirez")
    hz = S.crew_hazards(S.HourInputs(gust_mph=5.0, reports=[gusty]))[0]
    assert hz.severity == H.CREW_CONFIRMED_HIGH and hz.label.endswith("confirmed by J. Ramirez")


def test_predictive_floors_at_the_worst_report():
    x = S.HourInputs(reports=[report("fire", "high")])
    score, factors = S.crew_report_floor(0.4, [], x)
    assert score == 8.5 and factors[0]["key"] == "report_fire"
    assert S.crew_report_floor(0.4, [], S.HourInputs()) == (0.4, [])


def test_crew_report_alerts_are_not_scored_twice():
    alert = {"type": "crew_report", "severity": "danger", "title": "Crew report: fire (high)", "all_clear_at": None,
             "meta": {"source": "crew", "report_id": "x"}}
    assert S.alerts_at([alert], T0) == []  # the report itself is scored


# --- alerts for the site's team -----------------------------------------------------------------------------

def test_alert_rows_for_medium_and_high_reports():
    rid = uuid4()
    row = C.alert_row({"site_id": 621, "report_id": rid, "filed_on": 621, "hazard_type": "downed_line",
                       "severity": "high", "description": "Line down across the access road",
                       "reporter_name": "T. Nguyen", "created_at": T0, "confirmed_at": None})
    assert row["type"] == "crew_report" and row["severity"] == "danger" and row["dedupe_key"] == str(rid)
    assert row["title"] == "Crew report: downed line (high)"
    assert row["message"] == "Line down across the access road. Reported by T. Nguyen"
    assert row["meta"].obj["report_id"] == str(rid)  # the notification trigger pings once per report
    nearby = C.alert_row({"site_id": 622, "report_id": rid, "filed_on": 621, "hazard_type": "wildlife",
                          "severity": "medium", "description": None, "reporter_name": None, "created_at": T0,
                          "confirmed_at": T0})
    assert nearby["severity"] == "warning" and nearby["title"].endswith("(within 1 mile)")
    assert nearby["message"] == "Reported by the crew · confirmed by a manager"
    assert set(C.ALERT_SEVERITIES) == {"medium", "high"}  # low reports: map and score only


# --- the confirm route (mock mode) --------------------------------------------------------------------------

def test_managers_confirm_and_crew_cannot():
    gator = _FIXED_IDS["report-gator"]
    manager = TestClient(app, headers={"Authorization": "Dev manager"})
    r = manager.patch(f"/api/reports/{gator}/confirm")
    assert r.status_code == 200 and r.json()["confirmed_at"] is not None and r.json()["confirmed_by_name"]
    crew = TestClient(app, headers={"Authorization": "Dev crew"})
    assert crew.patch(f"/api/reports/{gator}/confirm").status_code == 403
    assert manager.patch(f"/api/reports/{uuid4()}/confirm").status_code == 404
