"""Pure-function tests for scripts/load_storm_events.py (no network, no database)."""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from load_storm_events import parse_damage, parse_local_time, to_event  # noqa: E402


def test_local_time_to_utc():
    assert parse_local_time("01-DEC-25 14:05:00", "EST-5") == datetime(2025, 12, 1, 19, 5, tzinfo=UTC)
    assert parse_local_time("15-JUL-24 23:30:00", "CST-6") == datetime(2024, 7, 16, 5, 30, tzinfo=UTC)
    assert parse_local_time("", "EST-5") is None
    with pytest.raises(ValueError):
        parse_local_time("01-DEC-25 14:05:00", "???")


def test_damage():
    assert parse_damage("10.00K") == 10_000
    assert parse_damage("1.5M") == 1_500_000
    assert parse_damage("0.00K") == 0
    assert parse_damage("250") == 250
    assert parse_damage("") is None


def test_to_event():
    row = {
        "EVENT_ID": "1299020", "EVENT_TYPE": "Lightning", "BEGIN_DATE_TIME": "03-AUG-25 15:10:00",
        "END_DATE_TIME": "03-AUG-25 15:10:00", "CZ_TIMEZONE": "EST-5", "STATE": "FLORIDA",
        "CZ_NAME": "MIAMI-DADE", "BEGIN_LAT": "25.44", "BEGIN_LON": "-80.33",
        "INJURIES_DIRECT": "1", "INJURIES_INDIRECT": "", "DEATHS_DIRECT": "", "DEATHS_INDIRECT": "0",
        "DAMAGE_PROPERTY": "2.00K",
    }
    event = to_event(row)
    assert event["event_id"] == 1299020
    assert event["begin_ts"] == datetime(2025, 8, 3, 20, 10, tzinfo=UTC)
    assert event["injuries"] == 1 and event["deaths"] == 0 and event["damage_usd"] == 2000
    assert event["latitude"] == 25.44
