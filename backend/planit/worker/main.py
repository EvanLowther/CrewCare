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
from planit.worker.ingest import nws, open_meteo, usgs
from planit.worker.rules import flood, lightning

log = logging.getLogger("planit.worker")

# name -> (function, seconds between runs). Enable a job by implementing its function.
JOBS = {
    "open_meteo": (open_meteo.poll, 1800),  # free-tier budget: 60 sites x 48 polls/day ~ 2,900 calls
    "nws": (nws.poll, 300),
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
