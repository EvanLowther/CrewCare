"""Owner: Person A. Background jobs: poll data sources, run hazard rules, score, brief.

Run: python dev.py worker
Each job is a plain function, so it can also be run once by hand:
    python -m planit.worker.main --once open_meteo
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from planit.ml import score
from planit.worker import jobs
from planit.worker.briefing import generate
from planit.worker.ingest import air_quality, earthquakes, nws, nws_weather, open_meteo, usgs, wildfire
from planit.worker.rules import flood, lightning

log = logging.getLogger("planit.worker")

# name -> (function, seconds between runs). Enable a job by implementing its function.
JOBS = {
    # Soil moisture, CAPE and the ML model's inputs: 160 sites x 8 polls/day x 1.4 ~ 1,800 of the 10,000 free calls
    "open_meteo": (open_meteo.poll, 10800),
    "nws_weather": (nws_weather.poll, 1800),  # Real-time weather: NWS forecast + station observations, no daily cap
    "nws": (nws.poll, 120),  # one national alerts request
    "air_quality": (air_quality.poll, 7200),  # smoke: PM2.5 AQI, ~1,900 Open-Meteo calls a day
    "wildfire": (wildfire.poll, 900),  # one national NIFC request
    "earthquakes": (earthquakes.poll, 120),  # one USGS feed request
    "usgs": (usgs.poll, 900),
    "lightning": (lightning.evaluate, 15),
    "flood": (flood.evaluate, 900),
    "score": (score.score_all, 300),
    "briefing": (generate.run_due, 300),  # sends each site's briefing at 6 PM site-local time
    "jobs": (jobs.poll, 2),  # demo buttons: job_requests rows inserted by the API
}


def _safe(name, fn):
    def run():
        try:
            fn()
        except NotImplementedError:
            log.debug("job %s not implemented yet", name)
        except Exception:
            log.exception("job %s failed", name)
    return run


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", choices=sorted(JOBS), help="Run one job once and exit")
    args = parser.parse_args()

    if args.once:
        JOBS[args.once][0]()
        return

    sched = BlockingScheduler(timezone="UTC")
    for name, (fn, seconds) in JOBS.items():
        sched.add_job(_safe(name, fn), "interval", seconds=seconds, id=name, max_instances=1, coalesce=True,
                      next_run_time=datetime.now(UTC))  # run once at startup, not only after the first interval
    log.info("worker started with jobs: %s", ", ".join(JOBS))
    sched.start()


if __name__ == "__main__":
    main()
