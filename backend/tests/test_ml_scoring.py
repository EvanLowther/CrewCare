"""ML path of planit.ml.score: window features and alert combination (pure functions, no database)."""

from datetime import UTC, datetime, timedelta

from planit.ml.features import FEATURES
from planit.ml.score import alerts_at, combine, smoke_floor, window_features

HOUR = datetime(2026, 8, 1, 15, tzinfo=UTC)


def hourly(rain_at: dict[int, float] | None = None, start=-100, end=30) -> list[dict]:
    """Hourly weather rows from HOUR+start to HOUR+end; rain_at maps hour offsets to inches."""
    rain_at = rain_at or {}
    return [{"ts": HOUR + timedelta(hours=h), "heat_index_f": 90.0 + (h == 2) * 15, "precip_in": rain_at.get(h, 0.0),
             "soil_moisture": 0.2, "gust_mph": 10.0 + (h == -5) * 30} for h in range(start, end)]


def test_window_features_use_24_h_around_the_hour():
    f = window_features(hourly({-12: 1.0, 11: 0.5, 12: 9.0, -13: 0.3, -90: 5.0}), HOUR)
    assert list(f) == FEATURES
    assert f["total_precip_in"] == 1.5  # -12 and +11 are in; +12 is the next window
    assert f["max_hourly_precip_in"] == 1.0
    assert f["precip_prev_3d_in"] == 0.3  # the 3 days before the window; -90 h is older than that
    assert f["max_heat_index_f"] == 105.0 and f["max_gust_mph"] == 40.0
    assert f["month"] == 8


def test_window_features_cold_snow_and_location():
    rows = [{"ts": HOUR + timedelta(hours=h), "temp_f": 10.0 - (h == 3) * 5, "wind_mph": 20.0, "humidity_pct": 60.0,
             "snowfall_in": 0.25, "snow_depth_ft": 0.5, "precip_in": 0.02} for h in range(-12, 12)]
    f = window_features(rows, HOUR, {"latitude": 47.4, "longitude": -101.2})
    assert f["min_temp_f"] == 5.0
    assert f["min_wind_chill_f"] == -15.4  # NWS chart: 5°F with 20 mph wind is -15
    assert f["total_snowfall_in"] == 6.0 and f["max_snow_depth_ft"] == 0.5
    assert f["latitude"] == 47.4 and f["longitude"] == -101.2


def test_window_features_warm_day_without_snow_data_has_no_snow():
    f = window_features(hourly(), HOUR)  # Florida-style rows: no temp, no snow columns
    assert f["total_snowfall_in"] is None and f["latitude"] is None
    warm = [{**r, "temp_f": 80.0} for r in hourly()]
    assert window_features(warm, HOUR)["total_snowfall_in"] == 0.0


def test_window_features_without_data():
    assert window_features([], HOUR) is None
    sparse = window_features(hourly(start=-12, end=-11), HOUR)  # one observed hour, no forecast yet
    assert sparse["precip_prev_3d_in"] is None and sparse["total_precip_in"] == 0.0


def test_combine_adds_alert_points_and_floors_at_the_alerts_real_time_severity():
    rain = [{"key": "rain_24h", "label": "2.0 in of rain in 24 h", "contribution": 3.0}]
    advisory = {"type": "wind", "severity": "warning", "title": "Wind Advisory", "nws_event": "Wind Advisory"}
    score, factors = combine(5.0, rain, [advisory])  # above the floor: just the points
    assert score == 6.2 and [f["key"] for f in factors] == ["rain_24h", "alert_wind"]

    score, factors = combine(0.2, [], [advisory])  # a calm-looking day with a Wind Advisory in force
    # The alert takes up the difference: the model's 0.2 + the alert's 4.3 = the 4.5 floor.
    assert score == 4.5 and factors[0] == {"key": "alert_wind", "label": "Wind Advisory", "contribution": 4.3}

    score, factors = combine(1.0, [], [{"type": "lightning", "severity": "danger", "title": "STOP WORK"}])
    assert score == 10.0 and factors[0]["label"] == "Lightning within 10 miles"  # Real-time: lightning is 10

    frost = {"type": "nws", "severity": "info", "title": "Frost Advisory", "nws_event": "Frost Advisory"}
    assert combine(0.2, [], [frost])[0] == 1.0  # frost isn't a crew hazard: floor 1.0
    assert combine(9.5, rain, [advisory])[0] == 10.0  # capped


def test_warning_floor_lifts_when_the_warning_ends():
    ends = (HOUR + timedelta(hours=3)).isoformat()
    alert = {"type": "wind", "severity": "warning", "title": "Wind Advisory issued", "all_clear_at": None,
             "meta": {"nws_event": "Wind Advisory", "ends": ends}}
    during = combine(0.3, [], alerts_at([alert], HOUR + timedelta(hours=1)))[0]
    after = combine(0.3, [], alerts_at([alert], HOUR + timedelta(hours=4)))[0]
    assert during == 4.5 and after == 0.3  # the forecast goes back down


def test_wildfire_alert_floors_predictive_at_its_rule_severity():
    fire = {"type": "wildfire", "severity": "danger", "title": "Creek Fire at the site", "all_clear_at": None,
            "meta": {"source": "nifc", "rule_severity": 9.5, "action": "Evacuate"}}
    score, factors = combine(0.5, [], alerts_at([fire], HOUR))  # the model can't see fire
    # The fire takes up the difference: the model's 0.5 + the alert's 9.0 = the 9.5 floor.
    assert score == 9.5 and factors[0]["key"] == "alert_wildfire" and factors[0]["contribution"] == 9.0


def test_smoke_floor_keeps_predictive_at_the_real_time_smoke_severity():
    rain = [{"key": "rain_24h", "label": "1.0 in of rain in 24 h", "contribution": 1.0}]
    score, factors = smoke_floor(1.0, rain, 200.0)  # AQI 200: smoke severity 5
    assert score == 5.0 and factors[0]["key"] == "smoke" and factors[0]["contribution"] == 4.0
    assert [f["key"] for f in factors] == ["smoke", "rain_24h"]
    assert smoke_floor(6.0, rain, 200.0) == (6.0, rain)  # already above it
    assert smoke_floor(1.0, rain, None) == (1.0, rain) and smoke_floor(1.0, rain, 80.0) == (1.0, rain)
