"""Owner: Person A. Hours 12-15.

Rule: any strike within settings.lightning_radius_mi (10) of a site -> active 'lightning' alert,
severity 'danger', dedupe_key 'lightning'. all_clear_at = latest nearby strike + 30 min, so every
new strike pushes it later. When now() > all_clear_at, set status 'cleared' and cleared_at.
meta: {"strike_count", "nearest_strike_mi", "last_strike_at"}.

Nearby strikes for a site:
    SELECT ... FROM lightning_strikes l JOIN sites s ON ST_DWithin(s.geom, l.geom, 16093.4)
    WHERE l.ts > now() - interval '30 minutes'
"""

from planit.models import LightningReplayRequest


def evaluate() -> None:
    raise NotImplementedError


def start_replay(req: LightningReplayRequest) -> None:
    """Insert strikes with source='replay' near req.site_id, one every req.interval_seconds (background thread)."""
    raise NotImplementedError
