"""Download observed hourly weather history for every site (ML training data).

    python scripts/backfill_weather.py 2023-01-01 2025-12-31
    python scripts/backfill_weather.py 2024-01-01 2025-12-31 --only-missing   # just sites with no history yet

Safe to re-run (upserts). Paced to Open-Meteo's hourly budget: ~70 minutes for 2 years x 100 sites.
Refreshes the weather_daily rollup for the same range at the end.
"""

import argparse
import logging
from datetime import date, timedelta

from planit.worker.ingest.open_meteo import backfill_history, refresh_daily_rollup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("start", help="First day, YYYY-MM-DD")
    parser.add_argument("end", help="Last day, YYYY-MM-DD")
    parser.add_argument("--only-missing", action="store_true",
                        help="Only sites with no observed weather on the start day (e.g. newly added sites)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    total = backfill_history(args.start, args.end, only_missing=args.only_missing)
    logging.info("weather rows written: %d; refreshing weather_daily", total)
    # The window must cover whole days, so end it at midnight after the last day.
    refresh_daily_rollup(args.start, (date.fromisoformat(args.end) + timedelta(days=1)).isoformat())
    logging.info("done")


if __name__ == "__main__":
    main()
