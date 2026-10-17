"""Owner: Person A. Demo controls for judging."""

from fastapi import APIRouter

from planit.api.deps import not_built, use_mock
from planit.models import DemoAck, LightningReplayRequest

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/lightning-replay", response_model=DemoAck)
def lightning_replay(req: LightningReplayRequest) -> DemoAck:
    """Start a storm near a site: strikes arrive every interval_seconds, each one resets the 30-min countdown."""
    if use_mock():
        return DemoAck(ok=True, message=f"Mock mode: would replay {req.strikes} strikes near site {req.site_id}")
    # TODO (hours 12-15): planit.worker.rules.lightning.start_replay(req)
    raise not_built("POST /api/demo/lightning-replay")
