"""Load NOAA Storm Events for the 50 states and DC into `storm_events` (labels for the hazard model).

    python scripts/load_storm_events.py            # every data/raw/**/StormEvents_details-*.csv.gz
    python scripts/load_storm_events.py FILE ...

Download the yearly "details" files from
https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/ into data/raw/ (git-ignored).
Marine areas (GULF OF MEXICO, LAKE ERIE, ...) and territories are skipped. `state` keeps NOAA's spelling
('FLORIDA'); planit.states maps it to the postal code. Safe to re-run (upsert on event_id).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import re
from collections import Counter
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from planit.states import STATE_CODES

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
BATCH = 5000  # rows per transaction, so one bad year doesn't hold a transaction open for minutes

_DAMAGE_UNITS = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def parse_local_time(value: str, cz_timezone: str) -> datetime | None:
    """'01-DEC-25 14:05:00' in 'EST-5' / 'CST-6' / 'EDT-4' -> aware UTC datetime."""
    if not value:
        return None
    match = re.search(r"([+-]\d+)$", cz_timezone or "")
    if not match:
        raise ValueError(f"Unknown CZ_TIMEZONE {cz_timezone!r}")
    local = datetime.strptime(value, "%d-%b-%y %H:%M:%S")
    return local.replace(tzinfo=timezone(timedelta(hours=int(match.group(1))))).astimezone(UTC)


def parse_damage(value: str) -> int | None:
    """'10.00K' -> 10000, '1.5M' -> 1500000, '' -> None."""
    value = (value or "").strip().upper()
    if not value:
        return None
    unit = value[-1] if value[-1] in _DAMAGE_UNITS else ""
    number = value[:-1] if unit else value
    return round(float(number or 0) * _DAMAGE_UNITS[unit])


def _int(value: str) -> int:
    return int(value) if value else 0


def _float(value: str) -> float | None:
    return float(value) if value else None


def to_event(row: dict) -> dict:
    return {
        "event_id": int(row["EVENT_ID"]),
        "event_type": row["EVENT_TYPE"],
        "begin_ts": parse_local_time(row["BEGIN_DATE_TIME"], row["CZ_TIMEZONE"]),
        "end_ts": parse_local_time(row["END_DATE_TIME"], row["CZ_TIMEZONE"]),
        "state": row["STATE"],
        "cz_name": row["CZ_NAME"],
        "latitude": _float(row["BEGIN_LAT"]),
        "longitude": _float(row["BEGIN_LON"]),
        "injuries": _int(row["INJURIES_DIRECT"]) + _int(row["INJURIES_INDIRECT"]),
        "deaths": _int(row["DEATHS_DIRECT"]) + _int(row["DEATHS_INDIRECT"]),
        "damage_usd": parse_damage(row["DAMAGE_PROPERTY"]),
    }


def read_events(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as f:
        return [to_event(r) for r in csv.DictReader(f) if r["STATE"] in STATE_CODES]


UPSERT_SQL = """
INSERT INTO storm_events (event_id, event_type, begin_ts, end_ts, state, cz_name, latitude, longitude,
                          injuries, deaths, damage_usd)
VALUES (%(event_id)s, %(event_type)s, %(begin_ts)s, %(end_ts)s, %(state)s, %(cz_name)s, %(latitude)s,
        %(longitude)s, %(injuries)s, %(deaths)s, %(damage_usd)s)
ON CONFLICT (event_id) DO UPDATE SET
    event_type = EXCLUDED.event_type, begin_ts = EXCLUDED.begin_ts, end_ts = EXCLUDED.end_ts,
    state = EXCLUDED.state, cz_name = EXCLUDED.cz_name, latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude, injuries = EXCLUDED.injuries, deaths = EXCLUDED.deaths,
    damage_usd = EXCLUDED.damage_usd
"""


def write(events: list[dict]) -> None:
    from planit.db import connection

    for i in range(0, len(events), BATCH):
        with connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.executemany(UPSERT_SQL, events[i:i + BATCH])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", type=Path, help="StormEvents details CSV(.gz) files")
    args = parser.parse_args()

    files = args.files or sorted(RAW_DIR.glob("**/StormEvents_details-*.csv*"))
    if not files:
        raise SystemExit(f"No Storm Events files in {RAW_DIR}. See the docstring for the download URL.")
    for path in files:
        events = read_events(path)
        write(events)
        types = Counter(e["event_type"] for e in events).most_common(6)
        states = len({e["state"] for e in events})
        print(f"{path.name}: {len(events)} events in {states} states. Top types: {types}")


if __name__ == "__main__":
    main()
