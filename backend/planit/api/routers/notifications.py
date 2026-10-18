"""Owner: Person B. Your notifications: the inbox, a live stream for open pages, and push to your devices."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from planit.api import mock, notifications_store
from planit.api.deps import use_mock
from planit.auth import SignedInUser
from planit.config import settings
from planit.models import MarkRead, NotificationList, PushKey, PushSubscriptionIn, PushUnsubscribe

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

STREAM_CHECK_SECONDS = 2.0
STREAM_PING_SECONDS = 15.0
# Each stream ends after this and the page reconnects with `after`, so a deploy's restart never waits on it.
STREAM_SECONDS = 120.0


@router.get("", response_model=NotificationList)
def list_notifications(user: SignedInUser, after: int | None = None) -> NotificationList:
    """Your latest 30 (newest first) and how many are unread. With `after`, only newer ones."""
    if use_mock():
        return mock.notifications(user)
    return notifications_store.list_notifications(user, after)


@router.post("/read", response_model=NotificationList)
def mark_read(req: MarkRead, user: SignedInUser) -> NotificationList:
    """Mark `ids` read, or all of them when `ids` is omitted."""
    if use_mock():
        return mock.notifications(user)
    notifications_store.mark_read(user, req.ids)
    return notifications_store.list_notifications(user)


@router.get("/stream")
async def stream(request: Request, user: SignedInUser, after: int | None = None) -> StreamingResponse:
    """Server-sent events: `notification` events (a Notification) as they're written, within ~2 s.

    Read it with fetch (EventSource can't send the sign-in token). Pass the newest id you have as `after` when
    reconnecting; the stream closes itself after a couple of minutes, so reconnect then too.
    """
    loop = asyncio.get_running_loop()

    async def events():
        if use_mock():
            last = after or 0
        else:
            last = after if after is not None else await asyncio.to_thread(notifications_store.newest_id, user)
        yield f"event: ready\ndata: {json.dumps({'after': last})}\n\n"
        end, next_ping = loop.time() + STREAM_SECONDS, loop.time() + STREAM_PING_SECONDS
        while loop.time() < end and not await request.is_disconnected():
            if not use_mock():
                new = await asyncio.to_thread(notifications_store.list_notifications, user, last)
                for n in reversed(new.notifications):
                    yield f"id: {n.id}\nevent: notification\ndata: {n.model_dump_json()}\n\n"
                    last = n.id
            if loop.time() >= next_ping:
                yield ": ping\n\n"
                next_ping = loop.time() + STREAM_PING_SECONDS
            await asyncio.sleep(STREAM_CHECK_SECONDS)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@router.get("/push-key", response_model=PushKey)
def push_key() -> PushKey:
    """The server's public VAPID key for PushManager.subscribe, or null when push isn't set up."""
    return PushKey(public_key=settings.vapid_public_key or None)  # an empty line in .env counts as unset


@router.post("/subscriptions", status_code=204)
def subscribe(sub: PushSubscriptionIn, request: Request, user: SignedInUser) -> None:
    """Send your notifications to this device (the browser's PushSubscription.toJSON())."""
    if not use_mock():
        notifications_store.save_subscription(user, sub, request.headers.get("user-agent"))


@router.post("/subscriptions/delete", status_code=204)
def unsubscribe(req: PushUnsubscribe, user: SignedInUser) -> None:
    """Stop sending to this device."""
    if not use_mock():
        notifications_store.delete_subscription(user, req.endpoint)
