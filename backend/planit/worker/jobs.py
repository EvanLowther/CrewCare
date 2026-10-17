"""Owner: Person A. Run demo-button requests from `job_requests` (the API inserts them; see migration 002).

Each poll claims the oldest pending request (SKIP LOCKED, so two workers never run the same one), runs the handler
for its `kind`, and marks it done or failed with the error. Handlers that start background work (lightning replay)
return once it has started.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from planit.db import connection

log = logging.getLogger(__name__)

CLAIM_SQL = """
UPDATE job_requests SET status = 'running', started_at = now()
WHERE id = (SELECT id FROM job_requests WHERE status = 'pending' ORDER BY requested_at
            FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING id, kind, params
"""
FINISH_SQL = "UPDATE job_requests SET status = %s, error = %s, finished_at = now() WHERE id = %s"

# kind -> handler(params). Filled in by the modules that own each job (e.g. rules/lightning.py).
HANDLERS: dict[str, Callable[[dict], None]] = {}


def poll() -> int:
    """Run every pending request; returns how many ran."""
    ran = 0
    while True:
        with connection() as conn:
            job = conn.execute(CLAIM_SQL).fetchone()
        if job is None:
            return ran
        handler = HANDLERS.get(job["kind"])
        try:
            if handler is None:
                raise NotImplementedError(f"no handler for job kind {job['kind']!r}")
            handler(job["params"])
            status, error = "done", None
        except Exception as exc:
            log.exception("job %s (%s) failed", job["id"], job["kind"])
            status, error = "failed", f"{type(exc).__name__}: {exc}"
        with connection() as conn:
            conn.execute(FINISH_SQL, (status, error, job["id"]))
        log.info("job %s (%s): %s", job["id"], job["kind"], status)
        ran += 1
