"""rules-v2 hazard curves, the NWS heat index, NWS event table and the combine rule (pure functions)."""

import pytest

from planit import hazards as H


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
