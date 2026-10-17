"""ML path of planit.ml.score: window features and alert combination (pure functions, no database)."""

from datetime import UTC, datetime, timedelta

from planit.ml.features import FEATURES
from planit.ml.score import LIGHTNING_FLOOR, combine, window_features

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


def test_window_features_without_data():
    assert window_features([], HOUR) is None
    sparse = window_features(hourly(start=-12, end=-11), HOUR)  # one observed hour, no forecast yet
    assert sparse["precip_prev_3d_in"] is None and sparse["total_precip_in"] == 0.0


def test_combine_adds_alerts_and_keeps_lightning_floor():
    rain = [{"key": "rain_24h", "label": "2.0 in of rain in 24 h", "contribution": 3.0}]
    warning = {"type": "wind", "severity": "warning", "title": "Wind Advisory"}
    score, factors = combine(3.0, rain, [warning])
    assert score == 4.2 and [f["key"] for f in factors] == ["rain_24h", "alert_wind"]

    score, factors = combine(1.0, [], [{"type": "lightning", "severity": "danger", "title": "STOP WORK"}])
    assert score == LIGHTNING_FLOOR and factors[0]["label"] == "Lightning within 10 miles"

    assert combine(9.5, rain, [warning])[0] == 10.0  # capped
