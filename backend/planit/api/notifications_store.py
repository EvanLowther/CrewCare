"""Owner: Person B. Your notifications: crew reports, danger alerts and briefings on the sites you're on.

Database triggers write them (migration 011), so this only reads them, marks them read and keeps the list of
devices that want them pushed (planit/api/push.py sends those).
"""

from __future__ import annotations

from planit.auth import CurrentUser
from planit.db import connection
from planit.models import Notification, NotificationList, PushSubscriptionIn

_COLS = "id, kind, site_id, severity, title, body, link, created_at, read_at IS NOT NULL AS read"


def _unread(conn, user: CurrentUser) -> int:
    return conn.execute("SELECT count(*) AS n FROM notifications WHERE user_id = %s AND read_at IS NULL",
                        (user.id,)).fetchone()["n"]


def list_notifications(user: CurrentUser, after: int | None = None, limit: int = 30) -> NotificationList:
    """Newest first. With `after`, only ones newer than that id (what the live stream sends)."""
    with connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLS} FROM notifications WHERE user_id = %(user)s AND (%(after)s::bigint IS NULL "
            "OR id > %(after)s) ORDER BY id DESC LIMIT %(limit)s",
            {"user": user.id, "after": after, "limit": limit},
        ).fetchall()
        return NotificationList(notifications=[Notification(**r) for r in rows], unread=_unread(conn, user))


def newest_id(user: CurrentUser) -> int:
    with connection() as conn:
        return conn.execute("SELECT coalesce(max(id), 0) AS id FROM notifications WHERE user_id = %s",
                            (user.id,)).fetchone()["id"]


def mark_read(user: CurrentUser, ids: list[int] | None) -> int:
    """Marks `ids` (or all) read; returns how many are still unread."""
    with connection() as conn:
        if ids is None:
            conn.execute("UPDATE notifications SET read_at = now() WHERE user_id = %s AND read_at IS NULL",
                         (user.id,))
        else:
            conn.execute("UPDATE notifications SET read_at = now() WHERE user_id = %s AND id = ANY(%s) "
                         "AND read_at IS NULL", (user.id, ids))
        return _unread(conn, user)


def save_subscription(user: CurrentUser, sub: PushSubscriptionIn, user_agent: str | None) -> None:
    """Remember this device. The same browser signing in as someone else moves the device to them."""
    with connection() as conn:
        conn.execute(
            "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (endpoint) DO UPDATE SET user_id = EXCLUDED.user_id, p256dh = EXCLUDED.p256dh, "
            "auth = EXCLUDED.auth, user_agent = EXCLUDED.user_agent",
            (user.id, sub.endpoint, sub.keys.p256dh, sub.keys.auth, (user_agent or "")[:300] or None),
        )


def delete_subscription(user: CurrentUser, endpoint: str) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM push_subscriptions WHERE user_id = %s AND endpoint = %s", (user.id, endpoint))
