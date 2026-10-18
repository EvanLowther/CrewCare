"""API contract: every JSON shape the frontend sees.

This file is the source of truth. After changing it, run `python dev.py types` to
regenerate frontend/src/lib/api-types.ts, and tell the other person.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "moderate", "high", "extreme"]
AlertType = Literal["lightning", "flood", "heat", "storm", "wind", "wildfire", "air_quality", "earthquake",
                    "crew_report", "nws"]
AlertSeverity = Literal["info", "warning", "danger"]
HazardType = Literal["wildlife", "flooding", "unstable_ground", "downed_line", "heat_illness", "fire", "other",
                     "lightning", "high_wind", "ice", "snow", "cold_stress", "smoke", "sinkhole", "fallen_tree",
                     "gas_leak", "earthquake_damage"]
ReportSeverity = Literal["low", "medium", "high"]
UserRole = Literal["admin", "manager", "crew"]
SiteRole = Literal["manager", "crew"]
NotificationKind = Literal["crew_report", "alert", "briefing"]


# --- Risk -------------------------------------------------------------------

class RiskFactor(BaseModel):
    key: str = Field(examples=["heat_index"])
    label: str = Field(examples=["Heat index 108°F · OSHA high risk"])
    contribution: float = Field(
        description="This hazard's own severity on the 0-10 scale (rules-v2); the worst one sets the score",
        examples=[6.0],
    )
    action: str | None = Field(
        default=None,
        description="What a supervisor should do about it, from the work rule behind the threshold",
        examples=["Limit exertion; enforce work/rest cycles; watch crews at all times"],
    )


class Risk(BaseModel):
    score: float = Field(ge=0, le=10, examples=[7.8])
    level: RiskLevel
    factors: list[RiskFactor] = Field(description="Top contributing factors, largest first")
    model_version: str = Field(examples=["rules-v2+xgb-2026-10-17"])
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


class AirQuality(BaseModel):
    """Latest air-quality reading for a site (Open-Meteo / CAMS model values, hourly)."""
    ts: datetime
    us_aqi: float | None = Field(description="US AQI, worst pollutant")
    us_aqi_pm2_5: float | None = Field(description="US AQI for PM2.5 alone (smoke): what the Real-time score uses")
    pm2_5_ugm3: float | None = Field(description="PM2.5, µg/m³")


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
    is_reference: bool = Field(default=True, description="Public reference site (anyone can view); false = private "
                               "site a manager created, visible to its members and admins")
    description: str | None = Field(default=None, description="Manager's note about the site, shown on its page")
    my_role: SiteRole | None = Field(default=None, description="The viewer's role on this site, if a member")
    can_manage: bool = Field(default=False, description="Viewer may edit the site, add members, resolve reports")
    can_delete: bool = Field(default=False, description="Viewer may delete the site")


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
    air_quality: AirQuality | None = Field(default=None, description="Latest air-quality hour, for smoke")
    forecast: list[Conditions] = Field(description="Next 48 hours, hourly")
    alerts: list[Alert] = Field(description="Active alerts for this site")
    reports: list[HazardReport] = Field(description="Active crew reports within 5 miles")
    risk_history: list[RiskPoint] = Field(description="Past 24 h + next 24 h forecast")


# --- Users, roles and site membership (docs/AUTH.md) --------------------------

class User(BaseModel):
    id: UUID
    name: str | None
    email: str | None
    picture: str | None = None
    role: UserRole


class MySite(BaseModel):
    site_id: int
    site_name: str
    role: SiteRole


class Me(BaseModel):
    user: User | None = Field(description="Null when signed out")
    sites: list[MySite] = Field(description="Sites the user is a member of")
    auth: Literal["auth0", "dev"] = Field(description="dev = the laptop 'Sign in as' menu (PLANIT_AUTH_DEV=1)")


class AdminUser(User):
    created_at: datetime
    last_seen_at: datetime
    site_count: int


class AdminUserList(BaseModel):
    users: list[AdminUser]


class RoleUpdate(BaseModel):
    role: UserRole


class UserList(BaseModel):
    users: list[User]


class SiteMember(BaseModel):
    user_id: UUID
    name: str | None
    email: str | None
    role: SiteRole
    added_at: datetime


class SiteMemberList(BaseModel):
    members: list[SiteMember]


class MemberAdd(BaseModel):
    user_id: UUID
    role: SiteRole = "crew"


class SiteCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120, examples=["Riverside substation rebuild"])
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    description: str | None = Field(default=None, max_length=2000,
                                    examples=["Trenching along the east fence; crane on site Tue-Thu."])


class SiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    description: str | None = Field(default=None, max_length=2000)


class GeocodeResult(BaseModel):
    label: str = Field(examples=["1600 Pennsylvania Avenue NW, Washington, DC"])
    latitude: float
    longitude: float


class GeocodeList(BaseModel):
    results: list[GeocodeResult] = Field(description="Best match first; US addresses and places only")


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
    generated_by: str = Field(examples=["gemini-3.5-flash", "template"])
    generated_at: datetime


class BriefingList(BaseModel):
    for_date: date
    briefings: list[Briefing]


# --- Notifications ----------------------------------------------------------

class Notification(BaseModel):
    """Something that happened on one of your sites: a crew report, a danger alert or the 6 PM briefing."""
    id: int = Field(description="Increases over time; pass the newest as `after` to get only newer ones")
    kind: NotificationKind
    site_id: int | None
    severity: AlertSeverity
    title: str = Field(examples=["Sinkhole reported at Big Bend"])
    body: str | None = None
    link: str | None = Field(default=None, description="Page to open, e.g. /sites/621")
    created_at: datetime
    read: bool


class NotificationList(BaseModel):
    notifications: list[Notification] = Field(description="Newest first")
    unread: int


class MarkRead(BaseModel):
    ids: list[int] | None = Field(default=None, description="Omit to mark all of them read")


class PushKey(BaseModel):
    public_key: str | None = Field(description="VAPID key for PushManager.subscribe; null when push is off")


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    """What the browser's PushSubscription.toJSON() returns."""
    endpoint: str = Field(max_length=2000)
    keys: PushSubscriptionKeys


class PushUnsubscribe(BaseModel):
    endpoint: str = Field(max_length=2000)


# --- Past hazards near a place ------------------------------------------------

class PastReport(BaseModel):
    id: UUID
    site_id: int | None
    site_name: str | None
    hazard_type: HazardType
    severity: ReportSeverity
    description: str | None
    created_at: datetime
    status: Literal["active", "resolved", "expired"]
    distance_mi: float


class PastStormEvent(BaseModel):
    event_id: int
    event_type: str = Field(examples=["Thunderstorm Wind", "Flash Flood"])
    begin_ts: datetime
    place: str | None = Field(description="NOAA's county or zone name, and state")
    distance_mi: float
    injuries: int
    deaths: int
    damage_usd: int


class EventTypeCount(BaseModel):
    event_type: str
    count: int


class LocationHistory(BaseModel):
    report_radius_mi: float = 5.0
    storm_radius_mi: float = 25.0
    reports: list[PastReport] = Field(description="Crew reports within report_radius_mi, newest first (max 50)")
    storm_events: list[PastStormEvent] = Field(
        description="NOAA Storm Events within storm_radius_mi, newest first (max 50)")
    storm_event_count: int = Field(description="All of them, not just the 50 listed")
    storm_event_types: list[EventTypeCount] = Field(description="Most common first")
    storm_years: str = Field(examples=["2024-2025"], description="Years the NOAA data covers")


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
