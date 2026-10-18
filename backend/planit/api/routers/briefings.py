"""Owner: Person B (endpoint) / Person A (generation job, worker/briefing/generate.py)."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb

from planit.api import mock, queries
from planit.api.deps import use_mock
from planit.auth import ManagerUser, OptionalUser
from planit.db import connection
from planit.models import BriefingList, DemoAck

router = APIRouter(prefix="/api/briefings", tags=["briefings"])


@router.get("", response_model=BriefingList)
def list_briefings(user: OptionalUser, for_date: date | None = None) -> BriefingList:
    """Briefings for a work day on the sites the viewer may see, riskiest first. Defaults to tomorrow."""
    day = for_date or (datetime.now(UTC).date() + timedelta(days=1))
    if use_mock():
        return BriefingList(for_date=day, briefings=mock.briefings(day))
    return BriefingList(for_date=day, briefings=queries.list_briefings(day, user))


@router.post("/generate", response_model=DemoAck)
def generate_now(user: ManagerUser) -> DemoAck:
    """Generate tomorrow's briefings now instead of waiting for 6 PM. Admins: every site. Managers: only the sites
    they manage.

    Queued in `job_requests`; the worker picks it up within ~2 s (it must be running). Poll GET /api/briefings to see
    them arrive. Each site's members are notified (once per site and day).
    """
    if use_mock():
        return DemoAck(ok=True, message="Mock mode: briefings are always available")
    with connection() as conn:
        if user.is_admin:
            conn.execute("INSERT INTO job_requests (kind) VALUES ('generate_briefings')")
            return DemoAck(ok=True, message="Generating tomorrow's briefings for every site: ready in about a minute")
        site_ids = [r["site_id"] for r in conn.execute(
            "SELECT site_id FROM site_members WHERE user_id = %s AND role = 'manager' ORDER BY site_id",
            (user.id,)).fetchall()]
        if not site_ids:
            raise HTTPException(409, "You don't manage any sites yet. Create one, or ask an admin to make you a "
                                     "site's manager.")
        conn.execute("INSERT INTO job_requests (kind, params) VALUES ('generate_briefings', %s)",
                     (Jsonb({"site_ids": site_ids}),))
    n = len(site_ids)
    return DemoAck(ok=True, message=f"Generating tomorrow's briefing for your {n} site{'s' if n != 1 else ''}: "
                                    "ready in about a minute")
