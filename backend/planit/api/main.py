"""FastAPI app. Run: python dev.py api  (http://localhost:8000/docs)"""

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from planit import db
from planit.api import push
from planit.api.routers import admin, alerts, briefings, demo, history, me, notifications, reports, sites, users
from planit.config import settings
from planit.models import Health


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Pushes new notifications to phones and browsers (off without VAPID keys).
    sender = asyncio.create_task(push.run_forever()) if push.enabled() else None
    yield
    if sender:
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender


app = FastAPI(title="Crew Care API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

for r in (sites.router, alerts.router, reports.router, briefings.router, demo.router, me.router, users.router,
          admin.router, notifications.router, history.router):
    app.include_router(r)


@app.get("/api/health", response_model=Health, tags=["health"])
def health() -> Health:
    return Health(status="ok", mock=settings.mock, database=db.check())
