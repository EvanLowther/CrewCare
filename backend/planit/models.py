"""API contract: every JSON shape the frontend sees.

This file is the source of truth. After changing it, run `make types` to
regenerate frontend/src/lib/api-types.ts, and tell the other person.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "moderate", "high", "extreme"]
AlertType = Literal["lightning", "flood", "heat", "storm", "wind", "wildfire", "crew_report", "nws"]
AlertSeverity = Literal["info", "warning", "danger"]
HazardType = Literal["wildlife", "flooding", "unstable_ground", "downed_line", "heat_illness", "fire", "other"]
ReportSeverity = Literal["low", "medium", "high"]


# --- Risk -------------------------------------------------------------------

class RiskFactor(BaseModel):
    key: str = Field(examples=["heat_index"])
    label: str = Field(examples=["Heat index 112°F"])
    contribution: float = Field(description="Points this factor adds to the 0-10 score", examples=[2.4])


class Risk(BaseModel):
    score: float = Field(ge=0, le=10, examples=[7.8])
    level: RiskLevel
    factors: list[RiskFactor] = Field(description="Top contributing factors, largest first")
    model_version: str = Field(examples=["rules-v1"])
    updated_at: datetime


class RiskPoint(BaseModel):
    ts: datetime
    score: float
    level: RiskLevel
    kind: Literal["current", "forecast"]


# --- Weather ----------------------------------------------------------------

class Conditions(BaseModel):
    ts: datetime
    temp_f: float | None
    heat_index_f: float | None
    humidity_pct: float | None
    precip_in: float | None
    precip_prob_pct: float | None
    wind_mph: float | None
    gust_mph: float | None
    cape_jkg: float | None
    soil_moisture: float | None = Field(description="m3/m3, 0-7 cm")
    weather_code: int | None


class Last24h(BaseModel):
    total_precip_in: float | None
    max_heat_index_f: float | None
    max_gust_mph: float | None


# --- Alerts -----------------------------------------------------------------

class Alert(BaseModel):
    id: UUID
    site_id: int
    site_name: str
    type: AlertType
    severity: AlertSeverity
    title: str = Field(examples=["STOP WORK: lightning within 10 miles"])
    message: str
    status: Literal["active", "cleared"]
    started_at: datetime
    all_clear_at: datetime | None = Field(
        description="Lightning only. Frontend counts down to this. Moves later with each new strike."
    )
    cleared_at: datetime | None
    meta: dict = Field(
        default_factory=dict,
        examples=[{"strike_count": 4, "nearest_strike_mi": 3.2, "last_strike_at": "2026-10-17T18:42:00Z"}],
    )
    updated_at: datetime


class AlertList(BaseModel):
    alerts: list[Alert]
    server_time: datetime = Field(description="Pass back as ?since= on the next poll")


# --- Sites ------------------------------------------------------------------

class SiteSummary(BaseModel):
    """One row on the dashboard map / ranked list."""
    id: int = Field(description="EIA plant code", examples=[621])
    name: str = Field(examples=["Turkey Point"])
    utility: str | None
    county: str | None
    plant_type: str | None
    capacity_mw: float | None
    latitude: float
    longitude: float
    timezone: str = Field(examples=["America/New_York"])
    risk: Risk | None = Field(description="Null until the first score is computed")
    active_alert_count: int
    top_alert: AlertType | None = Field(description="Most severe active alert type, for the map icon")
    heat_index_f: float | None


class SiteList(BaseModel):
    sites: list[SiteSummary] = Field(description="Sorted by risk score, highest first")
    updated_at: datetime


class HazardReport(BaseModel):
    id: UUID
    site_id: int | None
    latitude: float
    longitude: float
    hazard_type: HazardType
    severity: ReportSeverity
    description: str | None
    reporter_name: str | None
    photo_url: str | None = Field(description="Relative URL, e.g. /api/photos/{id}")
    status: Literal["active", "resolved"]
    created_at: datetime
    expires_at: datetime | None


class ReportList(BaseModel):
    reports: list[HazardReport]


class SiteDetail(BaseModel):
    """Everything the site page shows."""
    site: SiteSummary
    conditions: Conditions | None
    last_24h: Last24h | None
    forecast: list[Conditions] = Field(description="Next 48 hours, hourly")
    alerts: list[Alert] = Field(description="Active alerts for this site")
    reports: list[HazardReport] = Field(description="Active crew reports within 5 miles")
    risk_history: list[RiskPoint] = Field(description="Past 24 h + next 24 h forecast")


# --- Briefings --------------------------------------------------------------

class Briefing(BaseModel):
    id: UUID
    site_id: int
    site_name: str
    for_date: date
    summary: str = Field(examples=["Start before 7 AM. Heat index reaches 110°F by noon; storms likely after 2 PM."])
    details: dict = Field(
        default_factory=dict,
        examples=[{"peak_heat_index_f": 110, "storm_window": "2 PM - 6 PM", "risk_score": 7.4,
                   "recommendations": ["Water/rest/shade every hour after 11 AM"]}],
    )
    generated_by: str = Field(examples=["gemini-2.5-flash", "template"])
    generated_at: datetime


class BriefingList(BaseModel):
    for_date: date
    briefings: list[Briefing]


# --- Demo controls ----------------------------------------------------------

class LightningReplayRequest(BaseModel):
    site_id: int = Field(description="Center the storm on this site")
    strikes: int = Field(default=6, ge=1, le=50)
    interval_seconds: int = Field(default=20, ge=1, le=300, description="Time between strikes")


class DemoAck(BaseModel):
    ok: bool
    message: str


class Health(BaseModel):
    status: Literal["ok"]
    mock: bool = Field(description="True when serving sample data instead of the database")
    database: Literal["connected", "unavailable", "not_configured"]
