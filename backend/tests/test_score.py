"""rules-v2 site scores for real-world scenarios (pure functions, no database)."""

from datetime import UTC, datetime, timedelta

import pytest

from planit.ml.score import HourInputs, build_inputs, level_for, merge_weather, score_hour

T0 = datetime(2026, 1, 15, 12, tzinfo=UTC)


def test_merge_weather_prefers_nws_readings_but_keeps_open_meteo_rain_and_soil():
    om = [{"ts": T0, "temp_f": 30.0, "humidity_pct": 70, "precip_in": 0.8, "soil_moisture": 0.4, "gust_mph": 10,
           "cape_jkg": 0, "precip_prob_pct": 20, "weather_code": 3, "wind_mph": 5}]
    nws = [{"ts": T0, "temp_f": 5.0, "gust_mph": 35.0, "precip_in": 0.1, "visibility_m": None, "weather_code": None},
           {"ts": T0 + timedelta(hours=1), "temp_f": 4.0, "precip_in": 0.05, "wind_chill_f": -20.0}]
    first, second = merge_weather(om, nws)
    assert first["temp_f"] == 5.0 and first["gust_mph"] == 35.0  # NWS wins
    assert first["precip_in"] == 0.8 and first["weather_code"] == 3  # Open-Meteo kept where NWS has nothing better
    assert second["ts"] == T0 + timedelta(hours=1) and second["precip_in"] == 0.05  # NWS-only hour
    assert second["soil_moisture"] == 0.4 and second["wind_chill_f"] == -20.0


def test_build_inputs_totals_snow_and_ice_over_24_h():
    base = dict.fromkeys(("temp_f", "humidity_pct", "precip_in", "soil_moisture", "gust_mph", "cape_jkg",
                          "precip_prob_pct", "weather_code"))
    rows = [{**base, "ts": T0 - timedelta(hours=h), "temp_f": 25.0, "snowfall_in": 0.5, "ice_in": 0.02}
            for h in range(30)]
    x = build_inputs(sorted(rows, key=lambda r: r["ts"]), [], [T0])[T0]
    assert x.snow_24h_in == 12.0 and x.snow_1h_in == 0.5 and x.ice_24h_in == pytest.approx(0.48)
    score, factors = score_hour(x)
    assert score >= 9 and {f["key"] for f in factors} >= {"ice", "snow"}


def test_merge_weather_snow_from_open_meteo_ice_from_nws():
    om = [{"ts": T0, "temp_f": 20.0, "snowfall_in": 1.2}]
    nws = [{"ts": T0, "snowfall_in": 0.3, "ice_in": 0.04}, {"ts": T0 + timedelta(hours=1), "snowfall_in": 0.3}]
    first, second = merge_weather(om, nws)
    assert first["snowfall_in"] == 1.2 and first["ice_in"] == 0.04
    assert second["snowfall_in"] == 0.3


def test_bitter_wind_chill_and_dense_fog_score():
    assert score_hour(HourInputs(wind_chill_f=-25))[0] >= 7.5
    score, factors = score_hour(HourInputs(visibility_m=300))
    assert score >= 6 and factors[0]["key"] == "visibility"


def test_build_inputs_computes_wind_chill_when_nws_has_none():
    rows = [{"ts": T0, "temp_f": 0.0, "humidity_pct": 60, "precip_in": 0, "soil_moisture": None, "gust_mph": 20,
             "cape_jkg": None, "precip_prob_pct": None, "weather_code": None, "wind_mph": 15}]
    x = build_inputs(rows, [], [T0])[T0]
    assert x.wind_chill_f == pytest.approx(-19, abs=1)  # NWS chart: 0°F with 15 mph


def nws(event: str, alert_type: str = "nws", severity: str = "warning") -> dict:
    return {"type": alert_type, "severity": severity, "title": f"{event} issued ...", "nws_event": event}


def test_level_bands():
    assert [level_for(s) for s in (0, 2.4, 2.5, 4.9, 5, 7.4, 7.5, 10)] == [
        "low", "low", "moderate", "moderate", "high", "high", "extreme", "extreme"]


def test_calm_october_night_is_low():
    score, factors = score_hour(HourInputs(heat_index_f=74, rain_1h_in=0, rain_24h_in=0, rain_72h_in=0.1,
                                           soil_moisture=0.18, gust_mph=8, cape_jkg=300, precip_prob_pct=5,
                                           weather_code=1))
    assert level_for(score) == "low" and factors == []


def test_heat_alone_follows_osha():
    assert score_hour(HourInputs(heat_index_f=91))[0] == 2.5
    assert score_hour(HourInputs(heat_index_f=103))[0] == 5.0
    assert score_hour(HourInputs(heat_index_f=115))[0] == 9.0  # no strenuous work: stop-work territory
    assert score_hour(HourInputs(heat_index_f=125))[0] == 10.0


def test_lightning_is_always_10():
    score, factors = score_hour(HourInputs(heat_index_f=88, alerts=[
        {"type": "lightning", "severity": "danger", "title": "STOP WORK", "nearest_mi": 3.2}]))
    assert score == 10.0
    assert factors[0]["key"] == "lightning" and "30 min" in factors[0]["action"]


def test_forecast_thunderstorm_is_extreme():
    score, factors = score_hour(HourInputs(heat_index_f=96, weather_code=95, is_forecast=True))
    assert score >= 8.0 and factors[0]["label"] == "Thunderstorms forecast"


def test_gusts_over_the_aerial_lift_limit_are_high():
    score, factors = score_hour(HourInputs(gust_mph=30))
    assert level_for(score) == "high"
    assert factors[0]["action"] == "Ground aerial lifts and bucket trucks"


def test_wind_advisory_with_strong_gusts_is_high_not_doubled():
    score, factors = score_hour(HourInputs(gust_mph=38, alerts=[nws("Wind Advisory", "wind")]))
    assert level_for(score) == "high"
    assert {f["key"] for f in factors} == {"wind", "alert_wind"}


def test_flash_flood_warning_is_extreme():
    score, factors = score_hour(HourInputs(alerts=[nws("Flash Flood Warning", "flood", "danger")]))
    assert score >= 9.0 and factors[0]["label"] == "Flash Flood Warning"


def test_heat_with_modest_storm_energy_stays_high():
    heat_only = score_hour(HourInputs(heat_index_f=108))[0]
    score, _ = score_hour(HourInputs(heat_index_f=108, cape_jkg=2600, precip_prob_pct=60))
    assert score == heat_only == 6.0  # storm energy 1.9 isn't serious enough to compound
    assert score_hour(HourInputs(heat_index_f=108, weather_code=95))[0] == 9.5


def test_heavy_rain_on_saturated_ground():
    score, factors = score_hour(HourInputs(rain_24h_in=2.4, rain_72h_in=2.6, soil_moisture=0.41))
    assert score == 4.8 and level_for(score) == "moderate"  # same rain, counted once: soil 41% is the worse of the two
    assert factors[0]["key"] == "soil_moisture" and factors[0]["action"]
    assert level_for(score_hour(HourInputs(rain_24h_in=3.5, soil_moisture=0.45))[0]) == "high"


def test_build_inputs_windows_heat_index_and_alert_expiry():
    now = datetime(2026, 8, 1, 15, tzinfo=UTC)
    weather = [{"ts": now + timedelta(hours=h), "temp_f": 95.0, "humidity_pct": 55.0, "heat_index_f": 120.0,
                "precip_in": 0.5, "precip_prob_pct": 40.0, "soil_moisture": 0.3, "gust_mph": 20.0,
                "cape_jkg": 1500.0, "weather_code": 3} for h in range(-80, 5)]
    alerts = [{"type": "lightning", "severity": "danger", "title": "STOP", "all_clear_at": now + timedelta(minutes=20),
               "meta": {"nearest_strike_mi": 2.5}},
              {"type": "wind", "severity": "warning", "title": "Wind Advisory issued ...", "all_clear_at": None,
               "meta": {"nws_event": "Wind Advisory", "ends": (now + timedelta(hours=3)).isoformat()}}]
    inputs = build_inputs(weather, alerts, [now, now + timedelta(hours=2), now + timedelta(hours=4)])
    x = inputs[now]
    # NWS heat index from 95°F / 55% (chart: 106 at 94°F, 112 at 96°F), not the stored "feels like" 120
    assert x.heat_index_f == pytest.approx(109, abs=1)
    assert x.rain_1h_in == 0.5 and x.rain_24h_in == 12.0 and x.rain_72h_in == 36.0
    assert not x.is_forecast and inputs[now + timedelta(hours=2)].is_forecast
    assert {a["type"] for a in x.alerts} == {"lightning", "wind"}
    assert x.alerts[0]["nearest_mi"] == 2.5 and x.alerts[1]["nws_event"] == "Wind Advisory"
    assert [a["type"] for a in inputs[now + timedelta(hours=2)].alerts] == ["wind"]  # lightning cleared
    assert inputs[now + timedelta(hours=4)].alerts == []  # advisory ended
