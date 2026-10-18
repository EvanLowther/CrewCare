"""Owner: Person A. Lightning stop-work rule + countdown, and the demo replay.

Rule (OSHA/NOAA "when thunder roars"): any strike within settings.lightning_radius_mi (10) of a site -> one active
'lightning' alert per site (severity 'danger', dedupe_key 'lightning'). all_clear_at = the latest nearby strike +
settings.lightning_all_clear_min (30), so every new strike pushes the countdown back. When all_clear_at passes, the
alert is cleared. meta: {"strike_count", "nearest_strike_mi", "last_strike_at", "latest_strike_mi",
"latest_bearing", "strike_source"}; both scorers read it as a 10 (Predictive floors at the Real-time severity).

Live strikes come from GOES GLM (worker/ingest/glm.py, every 20 s). evaluate() runs every 15 s from the worker. The
replay (POST /api/demo/lightning-replay -> job_requests ->
start_replay()) drops strikes from a storm cell that drifts toward the site, one every interval_seconds, and runs
evaluate() after each so the banner and countdown move at once.
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from planit.config import settings
from planit.db import connection
from planit.models import LightningReplayRequest
from planit.worker import jobs

log = logging.getLogger(__name__)

METERS_PER_MILE = 1609.344
EARTH_RADIUS_MI = 3958.8
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# Per site: strikes within the radius in the countdown window, the latest and nearest of them.
NEARBY_SQL = """
WITH near AS (
    SELECT s.id AS site_id, s.timezone, l.ts, l.source,
           ST_Distance(s.geom, l.geom) / %(m_per_mi)s AS miles,
           degrees(ST_Azimuth(s.geom, l.geom)) AS bearing
    FROM lightning_strikes l
    JOIN sites s ON ST_DWithin(s.geom, l.geom, %(radius_m)s)
    WHERE l.ts > %(since)s AND l.ts <= %(now)s
)
SELECT site_id, max(timezone) AS timezone, count(*) AS strike_count, min(ts) AS first_strike_at,
       max(ts) AS last_strike_at, min(miles) AS nearest_mi,
       (array_agg(miles ORDER BY ts DESC))[1] AS latest_mi,
       (array_agg(bearing ORDER BY ts DESC))[1] AS latest_bearing,
       (array_agg(source ORDER BY ts DESC))[1] AS source
FROM near GROUP BY site_id
"""

# Only touch updated_at when the countdown or counts change, so ?since= polls only see real changes.
UPSERT_SQL = """
INSERT INTO alerts (site_id, type, severity, title, message, started_at, all_clear_at, dedupe_key, meta)
VALUES (%(site_id)s, 'lightning', 'danger', %(title)s, %(message)s, %(started_at)s, %(all_clear_at)s, 'lightning',
        %(meta)s)
ON CONFLICT (site_id, type, dedupe_key) WHERE status = 'active' DO UPDATE SET
    title = EXCLUDED.title, message = EXCLUDED.message, all_clear_at = EXCLUDED.all_clear_at,
    meta = EXCLUDED.meta, updated_at = now()
WHERE (alerts.message, alerts.all_clear_at, alerts.meta)
      IS DISTINCT FROM (EXCLUDED.message, EXCLUDED.all_clear_at, EXCLUDED.meta)
"""

CLEAR_SQL = """
UPDATE alerts SET status = 'cleared', cleared_at = all_clear_at, updated_at = now()
WHERE type = 'lightning' AND status = 'active' AND all_clear_at <= %(now)s
RETURNING site_id
"""

STRIKE_SQL = """
INSERT INTO lightning_strikes (ts, latitude, longitude, geom, source, peak_current_ka, replay_run_id)
VALUES (%(ts)s, %(lat)s, %(lon)s, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, 'replay',
        %(ka)s, %(run_id)s)
"""


def compass(bearing_deg: float | None) -> str:
    """Bearing from the site to the strike -> 8-point compass ('SW')."""
    if bearing_deg is None:
        return ""
    return COMPASS[round((bearing_deg % 360) / 45) % 8]


def _clock(ts: datetime, tz: str) -> str:
    return ts.astimezone(ZoneInfo(tz)).strftime("%I:%M %p").lstrip("0")


def alert_fields(agg: dict, all_clear_min: int | None = None, radius_mi: float | None = None) -> dict:
    """One NEARBY_SQL row -> the alert columns UPSERT_SQL takes."""
    all_clear_min = all_clear_min or settings.lightning_all_clear_min
    radius_mi = radius_mi or settings.lightning_radius_mi
    last = agg["last_strike_at"]
    all_clear = last + timedelta(minutes=all_clear_min)
    tz = agg.get("timezone") or "UTC"
    where = f"{agg['latest_mi']:.1f} mi {compass(agg['latest_bearing'])}".rstrip()
    return {
        "site_id": agg["site_id"],
        "title": f"STOP WORK: lightning within {radius_mi:g} miles",
        "message": (f"Strike {where} at {_clock(last, tz)}. All clear at {_clock(all_clear, tz)} "
                    f"({all_clear_min} min) if no new strikes."),
        "started_at": agg["first_strike_at"],
        "all_clear_at": all_clear,
        "meta": Jsonb({
            "strike_count": agg["strike_count"],
            "nearest_strike_mi": round(agg["nearest_mi"], 1),
            "latest_strike_mi": round(agg["latest_mi"], 1),
            "latest_bearing": compass(agg["latest_bearing"]),
            "last_strike_at": last.isoformat(),
            "strike_source": agg.get("source"),
        }),
    }


def evaluate(now: datetime | None = None) -> tuple[int, int]:
    """Open or extend each site's lightning alert, and clear the ones whose countdown ran out.
    Returns (sites with lightning nearby, alerts cleared)."""
    now = now or datetime.now(UTC)
    params = {"m_per_mi": METERS_PER_MILE, "radius_m": settings.lightning_radius_mi * METERS_PER_MILE,
              "since": now - timedelta(minutes=settings.lightning_all_clear_min), "now": now}
    with connection() as conn, conn.transaction(), conn.cursor() as cur:
        nearby = cur.execute(NEARBY_SQL, params).fetchall()
        if nearby:
            cur.executemany(UPSERT_SQL, [alert_fields(a) for a in nearby])
        cleared = cur.execute(CLEAR_SQL, {"now": now}).fetchall()
    if nearby or cleared:
        log.info("lightning: %d sites stop work, %d cleared", len(nearby), len(cleared))
    return len(nearby), len(cleared)


# --- Replay -------------------------------------------------------------------------------------------------

def destination(lat: float, lon: float, bearing_deg: float, miles: float) -> tuple[float, float]:
    """The point `miles` from (lat, lon) along `bearing_deg` (great circle)."""
    d, b = miles / EARTH_RADIUS_MI, math.radians(bearing_deg)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def replay_points(lat: float, lon: float, n: int, rng: random.Random) -> list[tuple[float, float]]:
    """A storm cell that starts 6-9 mi out and drifts to 2-4 mi from the site; strikes scatter around it."""
    bearing = rng.uniform(0, 360)
    start, end = rng.uniform(6, 9), rng.uniform(2, 4)
    points = []
    for i in range(n):
        miles = start + (end - start) * (i / (n - 1) if n > 1 else 1)
        points.append(destination(lat, lon, bearing + rng.uniform(-20, 20), max(0.5, miles + rng.uniform(-0.7, 0.7))))
    return points


def _run_replay(site_id: int, points: list[tuple[float, float]], interval_s: int, run_id: uuid.UUID,
                rng: random.Random) -> None:
    try:
        for i, (lat, lon) in enumerate(points):
            if i:
                time.sleep(interval_s)
            with connection() as conn:
                conn.execute(STRIKE_SQL, {"ts": datetime.now(UTC), "lat": lat, "lon": lon,
                                          "ka": round(rng.uniform(-40, 60), 1), "run_id": run_id})
            evaluate()
            log.info("replay %s: strike %d/%d near site %s", run_id, i + 1, len(points), site_id)
    except Exception:
        log.exception("lightning replay %s for site %s failed", run_id, site_id)


def start_replay(req: LightningReplayRequest) -> threading.Thread:
    """Start the storm in a background thread and return straight away (the job is 'done' once it starts)."""
    with connection() as conn:
        site = conn.execute("SELECT latitude, longitude FROM sites WHERE id = %s", (req.site_id,)).fetchone()
    if site is None:
        raise ValueError(f"site {req.site_id} not found")
    rng = random.Random()
    points = replay_points(site["latitude"], site["longitude"], req.strikes, rng)
    run_id = uuid.uuid4()
    thread = threading.Thread(target=_run_replay, args=(req.site_id, points, req.interval_seconds, run_id, rng),
                              name=f"lightning-replay-{req.site_id}", daemon=True)
    thread.start()
    log.info("replay %s: %d strikes near site %s, one every %ss", run_id, req.strikes, req.site_id,
             req.interval_seconds)
    return thread


jobs.HANDLERS["lightning_replay"] = lambda params: start_replay(LightningReplayRequest(**params))
