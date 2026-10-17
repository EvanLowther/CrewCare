"""FastAPI app. Run: make api  (http://localhost:8000/docs)"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from planit import db
from planit.api.routers import alerts, briefings, demo, reports, sites
from planit.config import settings
from planit.models import Health

app = FastAPI(title="PlanIT Control API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

for r in (sites.router, alerts.router, reports.router, briefings.router, demo.router):
    app.include_router(r)


@app.get("/api/health", response_model=Health, tags=["health"])
def health() -> Health:
    return Health(status="ok", mock=settings.mock, database=db.check())
