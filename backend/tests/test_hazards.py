"""rules-v2 hazard curves, the NWS heat index, NWS event table and the combine rule (pure functions)."""

import pytest

from planit import hazards as H


def test_national_nws_events_have_their_own_severity():
    assert H.nws_event("Freeze Warning", "Severe")[0] == 1.5  # crop frost, not the generic "Severe" 6.0
    assert H.nws_event("Blizzard Warning", "Severe")[0] == 9.0
    assert H.nws_event("Extreme Cold Warning", "Severe")[0] == 8.0
    assert "ice loading" in H.nws_event("Ice Storm Warning")[1]


def test_snow_by_rate_or_24h_total():
    assert H.snow(0.0, 0.2) is None
    assert H.snow(0.1, 6.0).severity == 6.5 and H.snow(0.1, 6.0).label == "6 in of snow in 24 h"
    heavy = H.snow(2.0, 2.0)
    assert heavy.severity == 7.5 and heavy.label == "Heavy snow 2.0 in/h" and "Postpone" in heavy.action
    assert H.snow(None, None) is None


def test_ice_quarter_inch_is_ice_storm_territory():
    assert H.ice(0.0) is None
    assert H.ice(0.25).severity == 7.5 and "ice loading" in H.ice(0.25).action
    assert H.ice(0.1).severity == 4.5
    assert H.KINDS["snow"] == H.KINDS["ice"] == "winter"


def test_cold_follows_the_wind_chill_chart():
    assert H.cold(40) is None
    assert H.cold(20).severity == 2.5 and "cold stress" in H.cold(20).action
    assert H.cold(0).severity == 5.0
    assert H.cold(-18).severity == 7.5 and "frostbite in 30 min" in H.cold(-18).label
    assert H.cold(-40).severity == 10.0
    assert H.cold(None) is None


def test_visibility_dense_fog_at_a_quarter_mile():
    assert H.visibility(16093) is None  # 10 mi
    assert H.visibility(1609.344).severity == 2.5 and "Headlights" in H.visibility(1609.344).action
    quarter = H.visibility(402.336)
    assert quarter.severity == 6.0 and "crane" in quarter.action and quarter.label == "Visibility 0.25 mi"
    assert H.visibility(100).severity == 7.5
    assert H.visibility(None) is None


def test_piecewise_interpolates_and_is_flat_beyond_the_ends():
    anchors = [(10, 0.0), (20, 5.0), (30, 6.0)]
    assert H.piecewise(5, anchors) == 0.0
    assert H.piecewise(15, anchors) == 2.5
    assert H.piecewise(25, anchors) == 5.5
    assert H.piecewise(99, anchors) == 6.0


@pytest.mark.parametrize(("temp_f", "rh", "chart"), [(90, 50, 95), (100, 40, 109), (96, 55, 112), (80, 40, 80)])
def test_nws_heat_index_matches_the_published_chart(temp_f, rh, chart):
    assert H.nws_heat_index(temp_f, rh) == pytest.approx(chart, abs=1.0)


def test_nws_heat_index_unknown_inputs():
    assert H.nws_heat_index(None, 50) is None
    assert H.nws_heat_index(90, float("nan")) is None


@pytest.mark.parametrize(("temp_f", "wind_mph", "chart"), [(30, 10, 21), (0, 15, -19), (-10, 30, -39), (5, 20, -15)])
def test_wind_chill_matches_the_nws_chart(temp_f, wind_mph, chart):
    assert H.wind_chill_f(temp_f, wind_mph) == pytest.approx(chart, abs=1.0)


def test_wind_chill_is_the_temperature_when_warm_or_calm():
    assert H.wind_chill_f(60, 20) == 60.0
    assert H.wind_chill_f(20, 2) == 20.0
    assert H.wind_chill_f(None, 10) is None


def test_heat_follows_osha_bands_with_115_as_stop_strenuous_work():
    assert [round(H.heat(hi).severity, 1) for hi in (91, 103, 108, 115, 125)] == [2.5, 5.0, 6.0, 9.0, 10.0]
    assert H.heat(78) is None  # below 80°F: nothing to show
    assert "OSHA: no strenuous work" in H.heat(116).label
    assert H.heat(116).action == "Stop strenuous work; reschedule non-essential tasks"
    assert "OSHA high risk" in H.heat(104).label


def test_wind_tracks_lift_limits():
    assert round(H.wind(20).severity, 1) == 2.5
    assert round(H.wind(28).severity, 1) == 5.0
    assert round(H.wind(40).severity, 1) == 7.5
    assert H.wind(58).severity == 10.0
    assert H.wind(30).action == "Ground aerial lifts and bucket trucks"
    assert "1926.1431" in H.wind(22).action
    assert H.wind(10) is None


def test_storms():
    assert H.lightning(3.2).severity == 10.0 and "3.2 mi" in H.lightning(3.2).label
    assert H.thunderstorm(95, forecast=True).severity == 8.0
    assert H.thunderstorm(99, forecast=False).label == "Thunderstorms with hail"
    assert H.thunderstorm(3, forecast=True) is None
    assert H.storm_potential(3500, 100).severity == 5.0
    assert H.storm_potential(800, 90) is None


def test_rain_and_ground():
    assert round(H.rain_rate(1.0).severity, 1) == 7.0 and "flash flooding" in H.rain_rate(1.2).label
    assert H.rain_24h(3.0).severity == 5.0
    assert H.ground(0.45, 0.0).severity == 6.0
    assert H.ground(0.20, 9.0).severity == 6.0  # capped: soft ground restricts, it doesn't stop work
    assert "3 days" in H.ground(0.20, 3.0).label
    assert H.ground(None, None) is None and H.ground(None, 0.2) is None


def test_nws_events_and_badges():
    assert H.nws_event("Tornado Warning")[0] == 10.0
    assert H.nws_event("wind advisory")[0] == 4.5  # case-insensitive
    assert H.nws_event("Brand New Product", "Severe") == (6.0, "Check the NWS alert for details")
    assert [H.badge_for(s) for s in (9.0, 7.5, 4.5, 3.0)] == ["danger", "danger", "warning", "info"]
    advisory = {"type": "wind", "severity": "warning", "title": "Wind Advisory issued...", "nws_event": "Wind Advisory"}
    hz = H.alert(advisory)
    assert (hz.key, hz.severity, hz.label) == ("alert_wind", 4.5, "Wind Advisory")


def test_combine_worst_sets_the_level_and_only_serious_hazards_compound():
    heat = H.heat(100)  # 4.4, OSHA moderate
    breeze = H.wind(21)  # 2.8: not serious enough to compound
    assert H.combine([heat, breeze])[0] == round(heat.severity, 1)

    storm = H.thunderstorm(95, forecast=True)  # 8
    score, factors = H.combine([H.heat(108), storm])
    assert score == 9.5  # 8 + 0.25 x 6
    assert [f["key"] for f in factors] == ["thunderstorm", "heat_index"]
    assert factors[0]["action"]


def test_combine_counts_each_kind_of_hazard_once():
    advisory = H.alert({"type": "wind", "severity": "warning", "title": "x", "nws_event": "Wind Advisory"})
    gusts = H.wind(38)
    assert H.combine([advisory, gusts])[0] == round(gusts.severity, 1)  # same wind, counted once
    rain, soil = H.rain_24h(2.4), H.ground(0.41, 2.6)  # same rain
    assert H.combine([rain, soil])[0] == round(max(rain.severity, soil.severity), 1)


def test_combine_without_hazards():
    assert H.combine([None, None]) == (0, [])


def test_smoke_follows_the_aqi_categories_and_cal_osha():
    assert H.smoke(None) is None and H.smoke(90) is None  # good / moderate air
    unhealthy = H.smoke(175)
    assert unhealthy.severity == 4.0 and unhealthy.label == "Air quality AQI 175 (smoke / PM2.5) · unhealthy"
    assert "N95" in unhealthy.action and "5141.1" in unhealthy.action
    assert H.smoke(200).severity == 5.0 and H.smoke(300).severity == 7.5
    assert H.smoke(650).severity == 10.0 and "Respirators required" in H.smoke(650).action


def test_wildfire_by_distance_to_the_edge_size_and_containment():
    # A 50,000-acre fire is ~5 mi across its radius: its reported point 5 mi off puts the edge at the site.
    big = H.wildfire("Creek", 5.0, 50_000, 20)
    assert big.severity == 9.5 and big.label == "Creek Fire at the site, 50,000 acres, 20% contained"
    assert "Evacuate" in big.action
    near = H.wildfire("PARK FIRE", 10.0, 1000, 0)  # edge ~9.3 mi
    assert near.severity == pytest.approx(5.3, abs=0.1) and near.label.startswith("Park Fire 9 mi away")
    assert H.wildfire("Park", 10.0, 1000, 95).severity == pytest.approx(near.severity / 2)
    assert H.wildfire("Park", 10.0, 1000, 100) is None  # contained
    assert H.wildfire("Park", 30.0, 1000, 0) is None  # out of range
    assert H.wildfire("Ridge", 12.0, 50, 0) is None and H.wildfire("Ridge", 8.0, 50, 0).severity > 5


def test_spot_fires_count_only_close_and_at_most_moderate():
    spot = H.wildfire("LAC-374499", 2.0, None, None)  # a dispatch record with no size yet
    assert spot.severity == H.SPOT_FIRE_CAP and spot.label == "Lac-374499 Fire 2 mi away, small"
    assert H.wildfire("LAC-374499", 6.0, 0.01, None) is None
    assert H.fire_edge_mi(3.0, None) == 3.0


@pytest.mark.parametrize(("region", "table"), [
    # USGS "Did You Feel It?" Atkinson-Wald 2007 curves for an M5.4 (event us70005dj8), at 41, 97, 251 and 717 km
    ("west", [4.01, 3.10, 1.98, 0.53]),
    ("east", [5.27, 4.32, 3.71, 2.44]),
])
def test_earthquake_intensity_reproduces_the_usgs_curves(region, table):
    distances = [41.1, 96.91, 251.38, 717.25]
    assert [round(H.earthquake_mmi(5.4, d, 0.0, region), 2) for d in distances] == table


def test_earthquake_severity_by_shaking():
    assert H.quake_region(-118.6) == "west" and H.quake_region(-89.6) == "east"
    assert H.mmi_roman(H.earthquake_mmi(6.0, 0.0, 0.0, "west")) == "VII"  # an M6 right under the site
    assert H.earthquake_mmi(3.0, 100 * H.KM_PER_MILE, 8.0, "west") < H.QUAKE_MIN_MMI  # an M3 100 mi off: nothing
    assert H.earthquake(3.0, 100, 2.1) is None
    strong = H.earthquake(6.0, 5, 7.0)
    assert strong.severity == 7.5 and strong.label == "M6.0 earthquake 5 mi away · shaking VII (est.)"
    assert "aftershocks" in strong.action
    assert H.earthquake(4.2, 3, 4.0).severity == 1.0


def test_alerts_scored_when_raised_keep_their_severity_and_kind():
    fire = H.alert({"type": "wildfire", "severity": "danger", "title": "Creek Fire at the site",
                    "rule_severity": 9.5, "action": "Evacuate"})
    assert (fire.key, fire.severity, fire.label, fire.action) == ("alert_wildfire", 9.5, "Creek Fire at the site",
                                                                   "Evacuate")
    red_flag = H.alert({"type": "wildfire", "severity": "warning", "title": "x", "nws_event": "Red Flag Warning"})
    assert H.combine([red_flag, fire])[0] == 9.5  # one fire danger, counted once
    smoke = H.smoke(250)  # smoke is its own kind: it compounds with the fire
    ridge = H.wildfire("Ridge", 9.0, 800, 0)  # ~5.6
    assert H.combine([ridge, smoke])[0] == round(smoke.severity + 0.25 * ridge.severity, 1)
    assert H.KINDS["smoke"] == H.KINDS["alert_air_quality"] == "air"


def test_miles_between():
    assert H.miles_between(25.435, -80.331, 25.435, -80.331) == 0
    assert H.miles_between(34.05, -118.25, 37.77, -122.42) == pytest.approx(347, abs=3)  # LA to San Francisco
