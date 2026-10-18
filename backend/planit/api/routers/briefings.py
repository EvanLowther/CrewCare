"""Owner: Person B (endpoint) / Person A (generation job, worker/briefing/generate.py)."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter

from planit.api import mock, queries
from planit.api.deps import use_mock
from planit.auth import AdminUser, OptionalUser
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
def generate_now(admin: AdminUser) -> DemoAck:
    """Admins only: generate tomorrow's briefings now instead of waiting for 6 PM.

    Queued in `job_requests`; the worker picks it up within ~2 s and writes every site's briefing (the worker must be
    running). Poll GET /api/briefings to see them arrive.
    """
    if use_mock():
        return DemoAck(ok=True, message="Mock mode: briefings are always available")
    with connection() as conn:
        conn.execute("INSERT INTO job_requests (kind) VALUES ('generate_briefings')")
    return DemoAck(ok=True, message="Generating tomorrow's briefings: ready in about a minute")
