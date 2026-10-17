"""Tests for the rules-v1 hazard score (pure functions, no database)."""

from datetime import UTC, datetime, timedelta

from planit.ml.score import HourInputs, build_inputs, heat_points, level_for, score_hour, storm_points


def test_level_bands():
    assert [level_for(s) for s in (0, 2.4, 2.5, 4.9, 5, 7.4, 7.5, 10)] == [
        "low", "low", "moderate", "moderate", "high", "high", "extreme", "extreme"]


def test_heat_points_follow_osha_bands():
    assert heat_points(85) == 0
    assert heat_points(103) == 1.5
    assert heat_points(115) == 3.5
    assert 1.5 < heat_points(110) < 3.0


def test_storm_points():
    assert storm_points(95, None, None) == 2.5
    assert storm_points(3, 500, 80) == 0
    assert storm_points(3, 3000, 100) == 2.0
    assert storm_points(3, 2000, 50) == 0.5


def test_calm_day_is_low():
    score, factors = score_hour(HourInputs(heat_index_f=84, rain_24h_in=0, soil_moisture=0.15, gust_mph=10,
                                           cape_jkg=300, precip_prob_pct=10, weather_code=1))
    assert score < 1 and level_for(score) == "low"


def test_hot_wet_stormy_day_is_high_with_true_labels():
    score, factors = score_hour(HourInputs(heat_index_f=112, rain_24h_in=2.4, soil_moisture=0.41, gust_mph=30,
                                           cape_jkg=2600, precip_prob_pct=70, weather_code=95))
    assert level_for(score) in ("high", "extreme")
    assert [f["key"] for f in factors] == ["heat_index", "thunderstorm", "rain_24h"]
    assert factors[0]["label"] == "Heat index 112°F"
    assert factors[2]["label"] == "2.4 in of rain in 24 h"


def test_lightning_floors_score_at_8_and_tops_factors():
    alerts = [{"type": "lightning", "severity": "danger", "title": "STOP WORK"},
              {"type": "nws", "severity": "danger", "title": "Wind Advisory"},
              {"type": "heat", "severity": "warning", "title": "Heat Advisory"}]
    score, factors = score_hour(HourInputs(heat_index_f=88, alerts=alerts))
    assert score >= 8.0
    assert factors[0]["label"] == "Lightning within 10 miles"
    assert len([f for f in factors if f["key"].startswith("alert_")]) == 2  # strongest + next only


def test_score_is_capped_at_10():
    score, _ = score_hour(HourInputs(heat_index_f=120, rain_24h_in=5, soil_moisture=0.5, gust_mph=60,
                                     weather_code=95,
                                     alerts=[{"type": "lightning", "severity": "danger", "title": "x"}]))
    assert score == 10.0


def test_build_inputs_rain_window_and_alert_expiry():
    now = datetime(2026, 8, 1, 15, tzinfo=UTC)
    weather = [{"ts": now + timedelta(hours=h), "heat_index_f": 100.0, "precip_in": 0.5, "precip_prob_pct": 40.0,
                "soil_moisture": 0.3, "gust_mph": 20.0, "cape_jkg": 1500.0, "weather_code": 3}
               for h in range(-30, 5)]
    alerts = [{"type": "lightning", "severity": "danger", "title": "STOP", "all_clear_at": now + timedelta(minutes=20),
               "meta": {}},
              {"type": "wind", "severity": "warning", "title": "Wind Advisory", "all_clear_at": None,
               "meta": {"nws_event": "Wind Advisory", "ends": (now + timedelta(hours=3)).isoformat()}}]
    inputs = build_inputs(weather, alerts, [now, now + timedelta(hours=2), now + timedelta(hours=4)])
    assert inputs[now].rain_24h_in == 12.0  # 24 hourly rows x 0.5 in
    assert {a["type"] for a in inputs[now].alerts} == {"lightning", "wind"}
    assert [a["type"] for a in inputs[now + timedelta(hours=2)].alerts] == ["wind"]  # lightning cleared
    assert inputs[now + timedelta(hours=4)].alerts == []  # advisory ended
    assert inputs[now].alerts[1]["title"] == "Wind Advisory"
