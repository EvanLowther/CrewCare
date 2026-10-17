"""Owner: Person A. Hours 4-8.

Hourly observations + 48 h forecast for every site -> `weather` table.
API: https://api.open-meteo.com/v1/forecast (no key). Batch many sites per request with
comma-separated latitude/longitude lists. Use temperature_unit=fahrenheit, wind_speed_unit=mph,
precipitation_unit=inch. apparent_temperature -> heat_index_f, soil_moisture_0_to_1cm -> soil_moisture.
Upsert on (site_id, ts, is_forecast).
"""


def poll() -> None:
    raise NotImplementedError


def backfill_history(start: str, end: str) -> None:
    """Historical hourly weather for ML training (https://archive-api.open-meteo.com/v1/archive)."""
    raise NotImplementedError
