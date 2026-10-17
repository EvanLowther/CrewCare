"""planit.ml.features on tiny in-memory frames: no database."""

import pandas as pd

from planit.ml.features import add_features, label_days, normalize_county

SITE = {"id": 1, "county": "Miami Dade", "latitude": 25.44, "longitude": -80.33}  # Turkey Point


def event(event_type="Thunderstorm Wind", begin="2024-06-01 18:00", end=None, cz="MONROE", lat=None, lon=None):
    return {"event_type": event_type, "begin_ts": pd.Timestamp(begin, tz="UTC"),
            "end_ts": pd.Timestamp(end, tz="UTC") if end else None, "cz_name": cz, "latitude": lat, "longitude": lon}


def labelled(*events):
    out = label_days(pd.DataFrame([SITE]), pd.DataFrame(list(events)))
    return [d.strftime("%Y-%m-%d") for d in out["day"]]


def test_normalize_county():
    assert normalize_county("MIAMI-DADE") == normalize_county("Miami Dade") == "MIAMI DADE"
    assert normalize_county("ST. JOHNS") == "ST JOHNS"
    assert normalize_county(None) == ""


def test_add_features_prev_3_day_rain_and_month():
    daily = pd.DataFrame({
        "site_id": [1] * 5,
        "day": pd.date_range("2024-01-30", periods=5, freq="D", tz="UTC"),
        "total_precip_in": [1.0, 2.0, 3.0, 4.0, 5.0],
    })
    out = add_features(daily.sample(frac=1, random_state=0))  # order must not matter
    assert out["precip_prev_3d_in"].tolist()[1:] == [1.0, 3.0, 6.0, 9.0]  # excludes the day itself
    assert pd.isna(out["precip_prev_3d_in"].iloc[0])
    assert out["month"].tolist() == [1, 1, 2, 2, 2]


def test_label_within_radius():
    assert labelled(event(lat=25.5, lon=-80.4)) == ["2024-06-01"]  # ~6 mi away
    assert labelled(event(lat=26.8, lon=-80.1)) == []  # Palm Beach, ~95 mi away


def test_label_same_county_without_coordinates():
    assert labelled(event("Excessive Heat", cz="MIAMI-DADE")) == ["2024-06-01"]
    assert labelled(event("Excessive Heat", cz="BROWARD")) == []


def test_label_ignores_non_hazard_types():
    assert labelled(event("Rip Current", cz="MIAMI-DADE"), event("Drought", cz="MIAMI-DADE")) == []


def test_multi_day_event_labels_at_most_three_days():
    hurricane = event("Hurricane (Typhoon)", begin="2024-10-09 12:00", end="2024-10-14 00:00", cz="MIAMI-DADE")
    assert labelled(hurricane) == ["2024-10-09", "2024-10-10", "2024-10-11"]


def test_duplicate_events_give_one_label():
    assert labelled(event(lat=25.5, lon=-80.4), event("Hail", cz="MIAMI-DADE")) == ["2024-06-01"]
