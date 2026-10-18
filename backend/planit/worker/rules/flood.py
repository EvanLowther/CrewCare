"""Owner: Person A. River flood-risk warnings: "sites along rivers, such as the Mississippi, get a flood-risk warning
after a night of heavy rain" (Sperry brief).

Every 15 min, for each site matched to a river gauge (ingest/river.py), hazards.river_flood() weighs the river now
(its NWS flood category), the NWS forecast for the next 48 h, and the last 12 h of rain at the site (observed
Open-Meteo, the totals the score uses). Any of them raises one 'flood' alert per site, dedupe_key 'river_flood',
meta.source 'river', with meta.rule_severity / meta.action for the scorers (an NWS Flood Warning is the same "water"
kind, so the score counts only the worse of the two).

It clears when the river is back below action stage, or, for a warning raised by the rain alone, 24 h after the rain
(meta.ends, which the scorer also honours).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from planit import hazards
from planit.db import connection
from planit.worker.ingest.nws import CLEAR_GONE, UPSERT_APP

log = logging.getLogger(__name__)

SOURCE = "river"
DEDUPE_KEY = "river_flood"
RAIN_WINDOW = timedelta(hours=12)
RAIN_ALERT_HOURS = 24
STALE_READING = timedelta(hours=6)  # an older gauge reading isn't "now"

RIVER_SITES_SQL = """
SELECT s.id AS site_id, g.gauge_id, g.name AS gauge_name, g.river, g.action_stage_ft, g.flood_stage_ft,
       g.moderate_stage_ft, g.major_stage_ft, l.ts AS reading_at, l.stage_ft, l.forecast_stage_ft, l.category
FROM sites s
JOIN river_gauges g ON g.gauge_id = s.usgs_gauge_id
LEFT JOIN LATERAL (SELECT ts, stage_ft, forecast_stage_ft, category FROM river_levels
                   WHERE gauge_id = g.gauge_id AND ts > %(fresh)s ORDER BY ts DESC LIMIT 1) l ON true
"""

RAIN_SQL = """
SELECT site_id, sum(precip_in) AS rain_in FROM weather
WHERE NOT is_forecast AND ts > %(since)s AND ts <= %(now)s AND site_id = ANY(%(ids)s)
GROUP BY site_id
"""

ACTIVE_SQL = """
SELECT site_id, meta FROM alerts WHERE status = 'active' AND type = 'flood' AND meta->>'source' = 'river'
"""


def stages_of(row: dict) -> dict:
    return {"action": row["action_stage_ft"], "minor": row["flood_stage_ft"], "moderate": row["moderate_stage_ft"],
            "major": row["major_stage_ft"]}


def alert_row(row: dict, rain_in: float | None, now: datetime) -> dict | None:
    """The flood-risk alert for one river site now, or None if neither the river nor the rain calls for one."""
    st = stages_of(row)
    river = row["river"] or row["gauge_name"]
    category = row["category"] if row["stage_ft"] is not None else None
    forecast_category = hazards.flood_category(row["forecast_stage_ft"], st)
    hazard = hazards.river_flood(river, rain_in, row["stage_ft"], category, row["forecast_stage_ft"],
                                 forecast_category, st)
    if hazard is None:
        return None
    by_river = category in hazards.RIVER_OBSERVED_SEVERITY or forecast_category in hazards.RIVER_FORECAST_SEVERITY
    ends = None if by_river else now + timedelta(hours=RAIN_ALERT_HOURS)
    stage = f"{row['stage_ft']:.1f} ft" if row["stage_ft"] is not None else "no recent reading"
    flood_at = f", flood stage {st['minor']:g} ft" if st["minor"] is not None else ""
    return {
        "site_id": row["site_id"],
        "type": "flood",
        "severity": hazards.badge_for(hazard.severity),
        "title": f"Flood risk: {hazard.label}",
        "message": f"{row['gauge_name']}: {stage}{flood_at}. {hazard.action}.",
        "started_at": now,
        "dedupe_key": DEDUPE_KEY,
        "meta": Jsonb({"source": SOURCE, "gauge_id": row["gauge_id"], "gauge": row["gauge_name"], "river": river,
                       "stage_ft": row["stage_ft"], "forecast_stage_ft": row["forecast_stage_ft"],
                       "category": category, "forecast_category": forecast_category,
                       "stages": st, "rain_12h_in": None if rain_in is None else round(rain_in, 2),
                       "rule_severity": round(hazard.severity, 1), "action": hazard.action,
                       "ends": ends.isoformat() if ends else None}),
    }


def still_in_force(meta: dict, now: datetime) -> bool:
    """A rain-only warning raised earlier stays up until its 24 h end."""
    ends = (meta or {}).get("ends")
    return ends is not None and datetime.fromisoformat(ends) > now


def evaluate(now: datetime | None = None) -> int:
    """Raise, refresh or clear each river site's flood-risk warning. Returns active warnings."""
    now = now or datetime.now(UTC)
    with connection() as conn:
        sites = conn.execute(RIVER_SITES_SQL, {"fresh": now - STALE_READING}).fetchall()
        ids = [s["site_id"] for s in sites]
        rain = {r["site_id"]: float(r["rain_in"]) for r in conn.execute(
            RAIN_SQL, {"since": now - RAIN_WINDOW, "now": now, "ids": ids}).fetchall() if r["rain_in"] is not None}
        active = {r["site_id"]: r["meta"] for r in conn.execute(ACTIVE_SQL).fetchall()}

    rows = [r for s in sites if (r := alert_row(s, rain.get(s["site_id"]), now)) is not None]
    keep = {r["site_id"] for r in rows} | {sid for sid, meta in active.items()
                                           if sid in ids and still_in_force(meta, now)}
    with connection() as conn, conn.transaction(), conn.cursor() as cur:
        if rows:
            cur.executemany(UPSERT_APP, rows)
        for site_id in set(ids) | set(active):  # also sites that lost their gauge (moved)
            cur.execute(CLEAR_GONE, {"source": SOURCE, "site_id": site_id,
                                     "keep": [DEDUPE_KEY] if site_id in keep else []})
    if rows or active:
        log.info("flood: %d river sites at risk (%d checked)", len(keep), len(ids))
    return len(keep)
