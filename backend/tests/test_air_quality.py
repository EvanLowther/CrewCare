"""Pure-function tests for the Open-Meteo air-quality ingest (no network, no database)."""

from datetime import UTC, datetime

from planit.worker.ingest.air_quality import COLUMNS, hourly_rows

HOURLY = {
    "time": ["2026-10-17T14:00", "2026-10-17T15:00", "2026-10-17T16:00"],
    "us_aqi": [62, 171, None],
    "us_aqi_pm2_5": [55, 171, None],
    "pm2_5": [13.1, 94.2, None],
}


def test_hourly_rows_mark_forecast_hours_and_skip_empty_ones():
    now = datetime(2026, 10, 17, 14, 30, tzinfo=UTC)
    rows = hourly_rows(9001, HOURLY, now)
    assert len(rows) == 2  # the all-null hour is skipped
    first, second = (dict(zip(COLUMNS, r, strict=True)) for r in rows)
    assert first == {"site_id": 9001, "ts": datetime(2026, 10, 17, 14, tzinfo=UTC), "is_forecast": False,
                     "us_aqi": 62, "us_aqi_pm2_5": 55, "pm2_5_ugm3": 13.1}
    assert second["is_forecast"] and second["us_aqi_pm2_5"] == 171
