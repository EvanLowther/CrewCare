"""Owner: Person B (endpoint) / Person A (generation job)."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter

from planit.api import mock
from planit.api.deps import not_built, use_mock
from planit.models import BriefingList, DemoAck

router = APIRouter(prefix="/api/briefings", tags=["briefings"])


@router.get("", response_model=BriefingList)
def list_briefings(for_date: date | None = None) -> BriefingList:
    """Briefings for a work day. Defaults to tomorrow."""
    day = for_date or (datetime.now(UTC).date() + timedelta(days=1))
    if use_mock():
        return BriefingList(for_date=day, briefings=mock.briefings(day))
    raise not_built("GET /api/briefings")


@router.post("/generate", response_model=DemoAck)
def generate_now() -> DemoAck:
    """Demo button: generate tomorrow's briefings immediately instead of waiting for 6 PM."""
    if use_mock():
        return DemoAck(ok=True, message="Mock mode: briefings are always available")
    # TODO (hours 19-21): call planit.worker.briefing.generate.generate_all()
    raise not_built("POST /api/briefings/generate")
