"""Owner: Person A. Active NWS alerts per site -> `nws_alerts`, mirrored into app `alerts`.

API: https://api.weather.gov/alerts/active?point={lat},{lon} (a User-Agent header is required).
App alerts made here carry meta.source = 'nws' and dedupe_key = the NWS alert id. They clear when
NWS stops listing them, but only for sites whose request succeeded this round, so a network blip
never clears a real warning. Cancellations, tests and marine/beach products (irrelevant to crews on
land) are skipped.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

import httpx
from psycopg.types.json import Jsonb

from planit.config import settings
from planit.db import connection

log = logging.getLogger(__name__)

ALERTS_URL = "https://api.weather.gov/alerts/active"
MESSAGE_MAX_CHARS = 400

# Checked in order; first match wins. Anything unmatched becomes type 'nws'.
_EVENT_TYPES = [
    ("heat", ("heat",)),
    ("flood", ("flood",)),
    ("storm", ("thunderstorm", "tornado", "hurricane", "tropical storm", "storm surge")),
    ("wind", ("wind",)),
    ("wildfire", ("red flag", "fire weather", "fire warning")),
]


# Marine and beach products reach coastal sites but aren't hazards for crews on land.
_IGNORED_EVENT_WORDS = ("small craft", "gale", "hazardous seas", "marine", "rip current", "high surf",
                        "beach hazard", "brisk wind", "low water", "special marine")


def is_relevant(properties: dict) -> bool:
    """Skip cancellations, test/exercise messages, and marine or beach-only products."""
    if properties.get("status") not in (None, "Actual") or properties.get("messageType") == "Cancel":
        return False
    event = (properties.get("event") or "").lower()
    return not any(w in event for w in _IGNORED_EVENT_WORDS)


def alert_type_for(event: str) -> str:
    name = event.lower()
    for alert_type, words in _EVENT_TYPES:
        if any(w in name for w in words):
            return alert_type
    return "nws"


def severity_for(nws_severity: str | None) -> str:
    return {"Extreme": "danger", "Severe": "danger", "Moderate": "warning"}.get(nws_severity or "", "info")


def short_message(description: str | None, instruction: str | None) -> str:
    """First paragraph of the description, plus what to do if NWS says so, trimmed for the UI."""
    text = " ".join((description or "").split("\n\n")[0].split())
    text = re.sub(r"^\*\s*[A-Z ]+\.\.\.\s*", "", text)  # NWS section label, e.g. "* WHAT..."
    if instruction:
        text = f"{text} {' '.join(instruction.split())}".strip()
    if len(text) > MESSAGE_MAX_CHARS:
        text = text[: MESSAGE_MAX_CHARS - 1].rsplit(" ", 1)[0] + "…"
    return text or "See NWS for details."


def _ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def to_rows(site_id: int, feature: dict) -> tuple[dict, dict]:
    """One NWS feature -> (nws_alerts row, app alerts row)."""
    p = feature["properties"]
    ends = _ts(p.get("ends")) or _ts(p.get("expires"))
    nws_row = {
        "alert_id": p["id"], "site_id": site_id, "event": p["event"], "severity": p.get("severity"),
        "headline": p.get("headline"), "description": p.get("description"), "onset": _ts(p.get("onset")),
        "ends": ends,
    }
    app_row = {
        "site_id": site_id,
        "type": alert_type_for(p["event"]),
        "severity": severity_for(p.get("severity")),
        "title": p.get("headline") or p["event"],
        "message": short_message(p.get("description"), p.get("instruction")),
        "started_at": _ts(p.get("onset")) or _ts(p.get("sent")) or datetime.now(UTC),
        "dedupe_key": p["id"],
        "meta": Jsonb({"source": "nws", "nws_event": p["event"], "nws_severity": p.get("severity"),
                       "ends": ends.isoformat() if ends else None}),
    }
    return nws_row, app_row


UPSERT_NWS = """
INSERT INTO nws_alerts (alert_id, site_id, event, severity, headline, description, onset, ends)
VALUES (%(alert_id)s, %(site_id)s, %(event)s, %(severity)s, %(headline)s, %(description)s, %(onset)s, %(ends)s)
ON CONFLICT (alert_id, site_id) DO UPDATE SET
    event = EXCLUDED.event, severity = EXCLUDED.severity, headline = EXCLUDED.headline,
    description = EXCLUDED.description, onset = EXCLUDED.onset, ends = EXCLUDED.ends, fetched_at = now()
"""

# Only touch updated_at when something visible changed, so polling clients aren't sent every row each time.
UPSERT_APP = """
INSERT INTO alerts (site_id, type, severity, title, message, started_at, dedupe_key, meta)
VALUES (%(site_id)s, %(type)s, %(severity)s, %(title)s, %(message)s, %(started_at)s, %(dedupe_key)s, %(meta)s)
ON CONFLICT (site_id, type, dedupe_key) WHERE status = 'active' DO UPDATE SET
    severity = EXCLUDED.severity, title = EXCLUDED.title, message = EXCLUDED.message, meta = EXCLUDED.meta,
    updated_at = now()
WHERE (alerts.severity, alerts.title, alerts.message, alerts.meta)
      IS DISTINCT FROM (EXCLUDED.severity, EXCLUDED.title, EXCLUDED.message, EXCLUDED.meta)
"""

CLEAR_GONE = """
UPDATE alerts SET status = 'cleared', cleared_at = now(), updated_at = now()
WHERE status = 'active' AND meta->>'source' = 'nws' AND site_id = %s AND NOT (dedupe_key = ANY(%s))
"""


def poll() -> int:
    """Fetch active alerts for every site; returns the number of active NWS alerts matched to sites."""
    with connection() as conn:
        sites = conn.execute("SELECT id, latitude, longitude FROM sites ORDER BY id").fetchall()

    per_site: dict[int, list[dict]] = {}
    headers = {"User-Agent": settings.nws_user_agent, "Accept": "application/geo+json"}
    with httpx.Client(headers=headers, timeout=30) as client:
        for site in sites:
            try:
                resp = client.get(ALERTS_URL, params={"point": f"{site['latitude']:.4f},{site['longitude']:.4f}"})
                resp.raise_for_status()
                per_site[site["id"]] = resp.json().get("features", [])
            except httpx.HTTPError as exc:
                log.warning("NWS request failed for site %s: %s", site["id"], exc)

    matched = 0
    with connection() as conn, conn.transaction(), conn.cursor() as cur:
        for site_id, features in per_site.items():
            rows = [to_rows(site_id, f) for f in features if is_relevant(f["properties"])]
            if rows:
                cur.executemany(UPSERT_NWS, [r[0] for r in rows])
                cur.executemany(UPSERT_APP, [r[1] for r in rows])
            cur.execute(CLEAR_GONE, (site_id, [r[1]["dedupe_key"] for r in rows]))
            matched += len(rows)
    log.info("nws poll: %d active alerts across %d/%d sites", matched, len(per_site), len(sites))
    return matched
