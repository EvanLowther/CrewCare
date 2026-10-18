"""Owner: Person A. Crew reports -> `crew_report` alerts, so a site's team hears about them in Alerts.

Every 60 s, each active medium or high report becomes an alert on the site it was filed on and on any site within
score.REPORT_RADIUS_MI (1 mi) of its pin: dedupe_key = the report id, meta.source 'crew', meta.report_id so the
notification triggers (migration 011) ping each person once for the report and its alert. Low reports go on the map
and in the score only. The alerts clear when the report is resolved or expires.

The score counts the reports themselves (score.crew_hazards: severity by type, confirmed by live data or a manager),
not these alerts, so nothing is counted twice.
"""

from __future__ import annotations

import logging

from psycopg.types.json import Jsonb

from planit.db import connection
from planit.ml.score import REPORT_RADIUS_MI
from planit.worker.ingest.nws import CLEAR_GONE, UPSERT_APP

log = logging.getLogger(__name__)

SOURCE = "crew"
ALERT_SEVERITIES = {"medium": "warning", "high": "danger"}

ACTIVE_REPORTS_SQL = """
SELECT s.id AS site_id, r.id AS report_id, r.site_id AS filed_on, r.hazard_type, r.severity, r.description,
       r.reporter_name, r.created_at, r.confirmed_at
FROM hazard_reports r
JOIN sites s ON s.id = r.site_id OR ST_DWithin(s.geom, r.geom, %(radius_m)s)
WHERE r.status = 'active' AND (r.expires_at IS NULL OR r.expires_at > now()) AND r.severity IN ('medium', 'high')
"""

SITES_WITH_CREW_ALERTS = "SELECT DISTINCT site_id FROM alerts WHERE status = 'active' AND meta->>'source' = 'crew'"


def alert_row(r: dict) -> dict:
    what = r["hazard_type"].replace("_", " ")
    where = "" if r["filed_on"] == r["site_id"] else " (within 1 mile)"
    by = f"Reported by {r['reporter_name']}" if r["reporter_name"] else "Reported by the crew"
    message = ". ".join(p for p in (r["description"], by + (" · confirmed by a manager" if r["confirmed_at"] else ""))
                        if p)
    return {
        "site_id": r["site_id"],
        "type": "crew_report",
        "severity": ALERT_SEVERITIES[r["severity"]],
        "title": f"Crew report: {what} ({r['severity']}){where}",
        "message": message,
        "started_at": r["created_at"],
        "dedupe_key": str(r["report_id"]),
        "meta": Jsonb({"source": SOURCE, "report_id": str(r["report_id"]), "hazard_type": r["hazard_type"],
                       "report_severity": r["severity"], "filed_on": r["filed_on"]}),
    }


def evaluate() -> int:
    """Raise or refresh an alert for each medium or high report, and clear the ones whose report is gone."""
    with connection() as conn:
        reports = conn.execute(ACTIVE_REPORTS_SQL, {"radius_m": REPORT_RADIUS_MI * 1609.344}).fetchall()
        alerted = {r["site_id"] for r in conn.execute(SITES_WITH_CREW_ALERTS).fetchall()}
    rows = [alert_row(r) for r in reports]
    keep: dict[int, list[str]] = {}
    for row in rows:
        keep.setdefault(row["site_id"], []).append(row["dedupe_key"])
    with connection() as conn, conn.transaction(), conn.cursor() as cur:
        if rows:
            cur.executemany(UPSERT_APP, rows)
        for site_id in alerted | keep.keys():
            cur.execute(CLEAR_GONE, {"source": SOURCE, "site_id": site_id, "keep": keep.get(site_id, [])})
    return len(rows)
