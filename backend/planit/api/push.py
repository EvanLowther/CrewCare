"""Owner: Person B. Sends new notifications to people's phones and browsers (Web Push).

Runs inside the API: every couple of seconds it claims notifications that haven't been pushed yet and sends each
to every device its person turned push on for. Claiming uses FOR UPDATE SKIP LOCKED, so the API's two workers
never send the same one twice. Devices the push service says are gone (404/410) are forgotten.

Off when the VAPID keys aren't set (laptops, CI), in mock mode, or without a database; notifications still show
in the app.
"""

from __future__ import annotations

import asyncio
import json
import logging

from planit.config import settings
from planit.db import connection

log = logging.getLogger("planit.push")

POLL_SECONDS = 2.0
# A notification older than this when the sender first sees it (the API was down, or push was just turned on)
# isn't pushed: a phone buzzing about yesterday's alert helps no one. It's still in the app.
MAX_AGE = "10 minutes"

_CLAIM_SQL = f"""
UPDATE notifications SET pushed_at = now()
WHERE id IN (SELECT id FROM notifications WHERE pushed_at IS NULL ORDER BY id LIMIT 100 FOR UPDATE SKIP LOCKED)
RETURNING id, user_id, kind, severity, title, body, link, created_at > now() - interval '{MAX_AGE}' AS fresh
"""


def enabled() -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_key and settings.database_url
                and not settings.mock)


def _payload(n: dict) -> str:
    # Read by frontend/public/sw.js.
    return json.dumps({"id": n["id"], "title": n["title"], "body": n["body"] or "", "url": n["link"] or "/",
                       "kind": n["kind"], "severity": n["severity"]})


def send_pending() -> int:
    """Claim and push every waiting notification once. Returns how many device sends succeeded."""
    from pywebpush import WebPushException, webpush  # only needed when push is on

    with connection() as conn:
        claimed = [n for n in conn.execute(_CLAIM_SQL).fetchall() if n["fresh"]]
        conn.commit()
        if not claimed:
            return 0
        subs = conn.execute(
            "SELECT id, user_id, endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = ANY(%s)",
            ([n["user_id"] for n in claimed],),
        ).fetchall()
    by_user: dict = {}
    for s in subs:
        by_user.setdefault(s["user_id"], []).append(s)

    sent, ok_ids, gone_ids = 0, set(), set()
    for n in claimed:
        for s in by_user.get(n["user_id"], []):
            if s["id"] in gone_ids:
                continue
            try:
                webpush(
                    subscription_info={"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}},
                    data=_payload(n),
                    vapid_private_key=settings.vapid_private_key,
                    vapid_claims={"sub": settings.vapid_subject},
                    ttl=3600,
                    headers={"Urgency": "high" if n["severity"] == "danger" else "normal"},
                    timeout=10,
                )
                sent += 1
                ok_ids.add(s["id"])
            except WebPushException as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in (404, 410):
                    gone_ids.add(s["id"])
                else:
                    log.warning("push to device %s failed: %s", s["id"], exc)
            except Exception:
                log.warning("push to device %s failed", s["id"], exc_info=True)

    if ok_ids or gone_ids:
        with connection() as conn:
            if ok_ids:
                conn.execute("UPDATE push_subscriptions SET last_ok_at = now() WHERE id = ANY(%s)", (list(ok_ids),))
            if gone_ids:
                conn.execute("DELETE FROM push_subscriptions WHERE id = ANY(%s)", (list(gone_ids),))
    return sent


async def run_forever() -> None:
    log.info("push sender on")
    while True:
        try:
            await asyncio.to_thread(send_pending)
        except Exception:
            log.warning("push sender pass failed", exc_info=True)
        await asyncio.sleep(POLL_SECONDS)
