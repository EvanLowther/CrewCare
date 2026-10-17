"""planit.worker.ingest.nws_weather on small NWS payloads (no network, no database)."""

from datetime import UTC, datetime

import pytest

from planit.worker.ingest.nws_weather import (
    COLUMNS,
    convert,
    expand,
    forecast_rows,
    observation_row,
    parse_interval,
    weather_codes,
)

NOW = datetime(2026, 10, 17, 19, 35, tzinfo=UTC)


def layer(uom, *values):
    return {"uom": f"wmoUnit:{uom}" if uom else None,
            "values": [{"validTime": t, "value": v} for t, v in values]}


def test_parse_interval():
    assert parse_interval("2026-10-17T12:00:00+00:00/PT1H") == (datetime(2026, 10, 17, 12, tzinfo=UTC), 1)
    assert parse_interval("2026-10-17T12:00:00+00:00/P1DT6H")[1] == 30
    assert parse_interval("2026-10-17T12:00:00+00:00/P5D")[1] == 120
    assert parse_interval("2026-10-17T12:00:00-05:00/PT30M") == (datetime(2026, 10, 17, 17, tzinfo=UTC), 1)
    with pytest.raises(ValueError):
        parse_interval("2026-10-17T12:00:00+00:00/whenever")


def test_convert_units():
    assert convert(0, "degC") == 32.0 and convert(-40, "degC") == -40.0
    assert convert(16.09344, "km_h-1") == 10.0
    assert convert(25.4, "mm") == 1.0
    assert convert(None, "degC") is None


def test_readings_repeat_and_amounts_split():
    temps = expand(layer("degC", ("2026-10-17T20:00:00+00:00/PT2H", 10.0)), "reading")
    assert list(temps.values()) == [10.0, 10.0]
    rain = expand(layer("mm", ("2026-10-17T18:00:00+00:00/PT6H", 12.0), ("2026-10-18T00:00:00+00:00/PT6H", None)),
                  "amount")
    assert len(rain) == 6 and set(rain.values()) == {2.0}


def test_weather_codes_only_when_likely():
    codes = weather_codes({"values": [
        {"validTime": "2026-10-17T20:00:00+00:00/PT2H",
         "value": [{"coverage": "likely", "weather": "thunderstorms"}]},
        {"validTime": "2026-10-17T22:00:00+00:00/PT1H",
         "value": [{"coverage": "slight_chance", "weather": "thunderstorms"}]},
        {"validTime": "2026-10-18T10:00:00+00:00/PT1H", "value": [{"coverage": "patchy", "weather": "fog"}]},
    ]})
    assert codes == {datetime(2026, 10, 17, 20, tzinfo=UTC): 95, datetime(2026, 10, 17, 21, tzinfo=UTC): 95,
                     datetime(2026, 10, 18, 10, tzinfo=UTC): 45}


def test_forecast_rows_start_after_now_in_store_units():
    grid = {
        "temperature": layer("degC", ("2026-10-17T19:00:00+00:00/PT3H", -10.0)),
        "windChill": layer("degC", ("2026-10-17T19:00:00+00:00/PT3H", -20.0)),
        "windGust": layer("km_h-1", ("2026-10-17T19:00:00+00:00/PT3H", 48.28)),
        "visibility": layer("m", ("2026-10-17T19:00:00+00:00/PT3H", 400.0)),
        "snowfallAmount": layer("mm", ("2026-10-17T18:00:00+00:00/PT6H", 30.48)),
        "probabilityOfThunder": layer(None, ("2026-10-17T19:00:00+00:00/PT3H", 10)),
    }
    rows = [dict(zip(COLUMNS, r, strict=True)) for r in forecast_rows(7, grid, NOW)]
    assert [r["ts"].hour for r in rows] == [20, 21]  # 19:00 is the current hour; the layer ends at 22:00
    first = rows[0]
    assert first["is_forecast"] and first["temp_f"] == 14.0 and first["wind_chill_f"] == -4.0
    assert first["gust_mph"] == 30.0 and first["visibility_m"] == 400.0
    assert first["snowfall_in"] == pytest.approx(0.2)  # 1.2 in over 6 h
    assert first["thunder_prob_pct"] == 10.0


def test_forecast_rows_reject_unexpected_units():
    with pytest.raises(ValueError, match="windGust"):
        forecast_rows(7, {"windGust": layer("m_s-1", ("2026-10-17T19:00:00+00:00/PT3H", 13.4))}, NOW)


def test_observation_row():
    obs = {"timestamp": "2026-10-17T19:35:00+00:00",
           "temperature": {"value": 23}, "relativeHumidity": {"value": 21.8}, "windSpeed": {"value": 16.56},
           "windGust": {"value": None}, "visibility": {"value": 16090}, "windChill": {"value": None},
           "presentWeather": [{"weather": "fog"}]}
    row = dict(zip(COLUMNS, observation_row(7, obs), strict=True))
    assert row["ts"] == datetime(2026, 10, 17, 19, tzinfo=UTC) and not row["is_forecast"]
    assert row["temp_f"] == 73.4 and row["wind_mph"] == 10.3 and row["gust_mph"] is None
    assert row["weather_code"] == 45
    assert observation_row(7, {"timestamp": "2026-10-17T19:35:00+00:00", "temperature": {"value": None}}) is None
