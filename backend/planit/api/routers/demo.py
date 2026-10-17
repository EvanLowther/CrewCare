"""Owner: Person A. Demo controls for judging."""

from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb

from planit.api.deps import use_mock
from planit.db import connection
from planit.models import DemoAck, LightningReplayRequest

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/lightning-replay", response_model=DemoAck)
def lightning_replay(req: LightningReplayRequest) -> DemoAck:
    """Start a storm near a site: strikes arrive every interval_seconds, each one resets the 30-min countdown.

    Queued in `job_requests`; the worker picks it up within ~2 s, so the worker must be running.
    """
    if use_mock():
        return DemoAck(ok=True, message=f"Mock mode: would replay {req.strikes} strikes near site {req.site_id}")
    with connection() as conn:
        site = conn.execute("SELECT name FROM sites WHERE id = %s", (req.site_id,)).fetchone()
        if site is None:
            raise HTTPException(404, "Site not found")
        conn.execute("INSERT INTO job_requests (kind, params) VALUES ('lightning_replay', %s)",
                     (Jsonb(req.model_dump()),))
    return DemoAck(ok=True, message=f"Storm queued near {site['name']}: first strike in a few seconds")
