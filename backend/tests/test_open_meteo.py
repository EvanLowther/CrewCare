"""Pure-function tests for the Open-Meteo ingest (no network, no database)."""

from datetime import UTC, date, datetime

from planit.worker.ingest.open_meteo import ARCHIVE_VARS, WEATHER_COLUMNS, chunks, hourly_rows, year_ranges


def test_year_ranges_split_on_calendar_years():
    assert list(year_ranges(date(2023, 6, 1), date(2025, 2, 1))) == [
        (date(2023, 6, 1), date(2023, 12, 31)),
        (date(2024, 1, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 2, 1)),
    ]


def test_chunks():
    assert list(chunks([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


HOURLY = {
    "time": ["2025-08-01T14:00", "2025-08-01T15:00", "2025-08-01T16:00"],
    "temperature_2m": [90.1, 91.0, None],
    "apparent_temperature": [101.0, 104.5, None],
    "relative_humidity_2m": [60, 58, None],
    "precipitation": [0.0, 0.2, None],
    "wind_speed_10m": [5.0, 7.0, None],
    "wind_gusts_10m": [12.0, 25.0, None],
    "weather_code": [1, 95, None],
    "soil_moisture_0_to_7cm": [0.31, 0.33, None],
}


def test_hourly_rows_maps_columns_and_skips_empty_hours():
    rows = hourly_rows(621, HOURLY, ARCHIVE_VARS)
    assert len(rows) == 2  # the all-null hour is dropped
    row = dict(zip(WEATHER_COLUMNS, rows[1], strict=True))
    assert row["site_id"] == 621
    assert row["ts"] == datetime(2025, 8, 1, 15, tzinfo=UTC)
    assert row["is_forecast"] is False
    assert row["heat_index_f"] == 104.5 and row["weather_code"] == 95 and row["soil_moisture"] == 0.33
    assert row["cape_jkg"] is None and row["precip_prob_pct"] is None


def test_hourly_rows_marks_future_hours_as_forecast():
    now = datetime(2025, 8, 1, 14, 30, tzinfo=UTC)
    rows = hourly_rows(621, HOURLY, ARCHIVE_VARS, now=now)
    assert [dict(zip(WEATHER_COLUMNS, r, strict=True))["is_forecast"] for r in rows] == [False, True]


def test_blend_soil_moisture_weights_layers_by_depth():
    from planit.worker.ingest.open_meteo import blend_soil_moisture

    hourly = {"time": ["a", "b", "c"],
              "soil_moisture_0_to_1cm": [0.10, None, None],
              "soil_moisture_1_to_3cm": [0.20, 0.30, None],
              "soil_moisture_3_to_9cm": [0.40, 0.30, None]}
    blended = blend_soil_moisture(hourly)["soil_moisture_0_to_7cm"]
    assert blended[0] == round((0.10 * 1 + 0.20 * 2 + 0.40 * 4) / 7, 4)
    assert blended[1] == 0.3  # missing layers are left out of the average
    assert blended[2] is None
