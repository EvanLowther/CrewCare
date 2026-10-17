"""planit.ml.features on tiny in-memory frames: no database."""

import pandas as pd

from planit.ml.features import add_features, label_days, normalize_county

SITE = {"id": 1, "state": "FL", "county": "Miami Dade", "latitude": 25.44, "longitude": -80.33}  # Turkey Point


def event(event_type="Thunderstorm Wind", begin="2024-06-01 18:00", end=None, cz="MONROE", lat=None, lon=None,
          state="FLORIDA"):
    return {"event_type": event_type, "begin_ts": pd.Timestamp(begin, tz="UTC"),
            "end_ts": pd.Timestamp(end, tz="UTC") if end else None, "state": state, "cz_name": cz,
            "latitude": lat, "longitude": lon}


def labelled(*events, site=SITE):
    out = label_days(pd.DataFrame([site]), pd.DataFrame(list(events)))
    return [d.strftime("%Y-%m-%d") for d in out["day"]]


def test_normalize_county():
    assert normalize_county("MIAMI-DADE") == normalize_county("Miami Dade") == "MIAMIDADE"
    assert normalize_county("ST. JOHNS") == normalize_county("St Johns")
    assert normalize_county("DE SOTO") == normalize_county("DeSoto")
    assert normalize_county(None) == ""


def test_normalize_county_strips_zone_words():
    miami = normalize_county("Miami Dade")
    for zone in ["COASTAL MIAMI-DADE COUNTY", "METROPOLITAN MIAMI-DADE", "FAR SOUTH MIAMI-DADE COUNTY"]:
        assert normalize_county(zone) == miami
    assert normalize_county("MONROE/LOWER KEYS") == normalize_county("Monroe")
    assert normalize_county("SOUTHERN BREVARD BARRIER ISLANDS") == normalize_county("Brevard")
    assert normalize_county("COASTAL HILLSBOROUGH") != normalize_county("Pinellas")


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
    assert labelled(event("Tropical Storm", cz="COASTAL MIAMI-DADE COUNTY")) == ["2024-06-01"]
    assert labelled(event("Excessive Heat", cz="BROWARD")) == []


def test_label_ignores_non_hazard_types():
    assert labelled(event("Rip Current", cz="MIAMI-DADE"), event("Drought", cz="MIAMI-DADE")) == []


def test_multi_day_event_labels_at_most_three_days():
    hurricane = event("Hurricane (Typhoon)", begin="2024-10-09 12:00", end="2024-10-14 00:00", cz="MIAMI-DADE")
    assert labelled(hurricane) == ["2024-10-09", "2024-10-10", "2024-10-11"]


def test_duplicate_events_give_one_label():
    assert labelled(event(lat=25.5, lon=-80.4), event("Hail", cz="MIAMI-DADE")) == ["2024-06-01"]


def test_same_county_name_in_another_state_does_not_label():
    brownlee = {"id": 2, "state": "ID", "county": "Washington", "latitude": 44.84, "longitude": -116.9}
    assert labelled(event("Winter Storm", cz="WASHINGTON", state="ALABAMA"), site=brownlee) == []
    assert labelled(event("Winter Storm", cz="WASHINGTON", state="IDAHO"), site=brownlee) == ["2024-06-01"]


def test_add_features_treats_missing_snow_on_warm_days_as_none():
    daily = pd.DataFrame({
        "site_id": [1, 1], "day": pd.date_range("2023-07-01", periods=2, freq="D", tz="UTC"),
        "total_precip_in": [0.0, 0.0], "min_temp_f": [75.0, 20.0],
        "total_snowfall_in": [None, None], "max_snow_depth_ft": [None, None],
    })
    out = add_features(daily)
    assert out["total_snowfall_in"].iloc[0] == 0.0 and out["max_snow_depth_ft"].iloc[0] == 0.0
    assert pd.isna(out["total_snowfall_in"].iloc[1])  # a freezing day without data stays unknown
