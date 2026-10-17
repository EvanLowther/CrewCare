"""Owner: Person B (endpoint) / Person A (rules that create alerts).

The frontend polls GET /api/alerts?since=<server_time from last poll> every ~10 s.
"""

from datetime import UTC, datetime

from fastapi import APIRouter

from planit.api import mock, queries
from planit.api.deps import use_mock
from planit.auth import OptionalUser
from planit.models import AlertList

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=AlertList)
def list_alerts(user: OptionalUser, site_id: int | None = None, since: datetime | None = None,
                include_cleared: bool = False) -> AlertList:
    """Active alerts on sites the viewer may see. With `since`, only alerts updated after that time (includes newly
    cleared ones)."""
    now = datetime.now(UTC)
    if use_mock():
        return AlertList(alerts=mock.alerts(site_id), server_time=now)
    return AlertList(alerts=queries.list_alerts(site_id, since, include_cleared, user), server_time=now)
