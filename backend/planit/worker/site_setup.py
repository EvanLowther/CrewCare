"""Owner: Person A. Weather and both scores for a site a manager just created or moved, in about a minute.

The API queues a 'site_setup' job request with {"site_id"} (api/sites_store.py); the `jobs` poller runs it within
~2 s. Without it the site would wait for the regular polls: NWS weather up to 30 min, Open-Meteo (the Predictive
model's inputs) up to 3 h, with only one past day of rain for its first days.

For that one site: link it to its NWS grid and alert zones and fetch the NWS forecast and observation; Open-Meteo
with SETUP_PAST_DAYS of history (the model's 12 h window plus the 3 days of rain before it, and Real-time's 72 h
rain for saturated ground); air quality. Then the national alerts, fires and quakes (one request each), and a
rescore of every site, so both scores show on the site's page straight away. The model is national (latitude and
longitude are inputs), so it scores any US location without retraining.
"""

from __future__ import annotations

import logging

from planit.db import connection
from planit.ml import score
from planit.worker import jobs
from planit.worker.ingest import air_quality, earthquakes, nws, nws_weather, open_meteo, wildfire

log = logging.getLogger(__name__)

SETUP_PAST_DAYS = 5


def run(site_id: int) -> bool:
    """Set the site up; False if it no longer exists (deleted before the job ran)."""
    with connection() as conn:
        if conn.execute("SELECT 1 FROM sites WHERE id = %s", (site_id,)).fetchone() is None:
            log.info("site setup: site %s is gone", site_id)
            return False
    nws_weather.poll(site_ids=[site_id])  # links the grid and alert zones first
    open_meteo.poll(site_ids=[site_id], past_days=SETUP_PAST_DAYS)
    air_quality.poll(site_ids=[site_id])
    for poll in (nws.poll, wildfire.poll, earthquakes.poll):  # alerts for its location
        try:
            poll()
        except Exception:  # an alert source being down mustn't stop the scores
            log.exception("site setup: %s failed", poll.__module__)
    score.score_all()
    log.info("site setup: site %s ready", site_id)
    return True


jobs.HANDLERS["site_setup"] = lambda params: run(int(params["site_id"]))
