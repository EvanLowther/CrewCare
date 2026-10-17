"""Sample data in the exact API shapes, served when PLANIT_MOCK=1.

Lets the frontend be built before the database has real data. Coordinates are
approximate and the plant codes are placeholders; real sites come from
EIA-860M via scripts/load_sites.py.
"""

from __future__ import annotations

import math
import random
import uuid
from datetime import UTC, date, datetime, timedelta

from planit.models import (
    Alert,
    Briefing,
    Conditions,
    HazardReport,
    Last24h,
    Risk,
    RiskFactor,
    RiskPoint,
    SiteDetail,
    SiteSummary,
)

# (id, name, utility, county, plant_type, capacity_mw, lat, lon, timezone)
_SITES = [
    (9001, "Turkey Point", "Florida Power & Light", "Miami-Dade", "Nuclear", 2300, 25.435, -80.331, "America/New_York"),
    (9002, "St. Lucie", "Florida Power & Light", "St. Lucie", "Nuclear", 1980, 27.348, -80.246, "America/New_York"),
    (9003, "Martin Clean Energy Center", "Florida Power & Light", "Martin", "Natural Gas Fired Combined Cycle", 3700, 27.053, -80.563, "America/New_York"),
    (9004, "Crystal River", "Duke Energy Florida", "Citrus", "Natural Gas Fired Combined Cycle", 1640, 28.959, -82.698, "America/New_York"),
    (9005, "Big Bend", "Tampa Electric", "Hillsborough", "Natural Gas Fired Combined Cycle", 1800, 27.794, -82.403, "America/New_York"),
    (9006, "Port Everglades", "Florida Power & Light", "Broward", "Natural Gas Fired Combined Cycle", 1250, 26.085, -80.120, "America/New_York"),
    (9007, "Northside Generating Station", "JEA", "Duval", "Petroleum Coke", 1300, 30.420, -81.553, "America/New_York"),
    (9008, "Fort Myers", "Florida Power & Light", "Lee", "Natural Gas Fired Combined Cycle", 1720, 26.697, -81.783, "America/New_York"),
    (9009, "Crist", "Gulf Power", "Escambia", "Natural Gas Fired Combined Cycle", 950, 30.565, -87.226, "America/Chicago"),
    (9010, "Lansing Smith", "Gulf Power", "Bay", "Natural Gas Fired Combined Cycle", 560, 30.268, -85.700, "America/Chicago"),
    (9011, "Everglades Solar Energy Center", "Florida Power & Light", "Miami-Dade", "Solar Photovoltaic", 75, 25.620, -80.480, "America/New_York"),
    (9012, "Sanford", "Florida Power & Light", "Volusia", "Natural Gas Fired Combined Cycle", 1900, 28.842, -81.325, "America/New_York"),
]

_SCORES = {9001: 8.4, 9011: 7.9, 9003: 6.6, 9008: 6.1, 9006: 5.2, 9002: 4.8,
           9005: 4.1, 9004: 3.6, 9012: 3.0, 9007: 2.4, 9010: 1.9, 9009: 1.2}

_FIXED_IDS = {name: uuid.uuid5(uuid.NAMESPACE_URL, f"planit-mock/{name}") for name in
              ["lightning", "heat", "flood", "report-gator", "report-mud"]}


def _now() -> datetime:
    return datetime.now(UTC).replace(second=0, microsecond=0)


def _level(score: float) -> str:
    if score >= 7.5:
        return "extreme"
    if score >= 5:
        return "high"
    if score >= 2.5:
        return "moderate"
    return "low"


def _risk(site_id: int) -> Risk:
    score = _SCORES[site_id]
    # Same shape as rules-v2: each factor's contribution is that hazard's own 0-10 severity, worst first.
    factors = [
        RiskFactor(key="heat_index", label=f"Heat index {round(96 + score * 2)}°F · OSHA high risk",
                   contribution=round(score * 0.9, 1),
                   action="Limit exertion; enforce work/rest cycles; watch crews at all times"),
        RiskFactor(key="soil_moisture", label="Saturated ground (soil moisture 41%)", contribution=round(score * 0.5, 1),
                   action="Use matting or tracked equipment on unpaved access"),
        RiskFactor(key="thunderstorm", label="Storm energy (CAPE 2,600, 60% rain chance)",
                   contribution=round(score * 0.3, 1), action=None),
    ]
    return Risk(score=score, level=_level(score), factors=factors, model_version="mock", updated_at=_now())


def _conditions(site_id: int, ts: datetime) -> Conditions:
    rng = random.Random(f"{site_id}-{ts.isoformat()}")
    hour = ts.hour - 4  # rough Florida local hour
    daily = math.sin((hour - 9) / 24 * 2 * math.pi)
    temp = 84 + 8 * daily + rng.uniform(-1, 1)
    return Conditions(
        ts=ts,
        temp_f=round(temp, 1),
        heat_index_f=round(temp + 10 + _SCORES[site_id], 1),
        humidity_pct=round(70 - 10 * daily + rng.uniform(-3, 3)),
        precip_in=round(max(0.0, rng.uniform(-0.2, 0.3)), 2),
        precip_prob_pct=round(min(100, max(0, 30 + 40 * daily + rng.uniform(-10, 10)))),
        wind_mph=round(rng.uniform(4, 14), 1),
        gust_mph=round(rng.uniform(12, 28), 1),
        cape_jkg=round(max(0, 1500 + 1500 * daily + rng.uniform(-300, 300))),
        soil_moisture=round(0.30 + _SCORES[site_id] * 0.012, 3),
        weather_code=rng.choice([1, 2, 3, 61, 80, 95]),
    )


def _alerts() -> list[Alert]:
    now = _now()
    return [
        Alert(
            id=_FIXED_IDS["lightning"], site_id=9001, site_name="Turkey Point", type="lightning", severity="danger",
            title="STOP WORK: lightning within 10 miles",
            message="Strike 3.2 mi SW at 2:42 PM. All clear in 30 minutes if no new strikes.",
            status="active", started_at=now - timedelta(minutes=12), all_clear_at=now + timedelta(minutes=24),
            cleared_at=None,
            meta={"strike_count": 4, "nearest_strike_mi": 3.2,
                  "last_strike_at": (now - timedelta(minutes=6)).isoformat()},
            updated_at=now - timedelta(minutes=6),
        ),
        Alert(
            id=_FIXED_IDS["heat"], site_id=9011, site_name="Everglades Solar Energy Center", type="heat",
            severity="warning", title="Heat advisory: heat index 112°F",
            message="Mandatory water/rest/shade breaks every 30 minutes until 6 PM.",
            status="active", started_at=now - timedelta(hours=2), all_clear_at=None, cleared_at=None,
            meta={"heat_index_f": 112, "nws_event": "Heat Advisory"}, updated_at=now - timedelta(hours=2),
        ),
        Alert(
            id=_FIXED_IDS["flood"], site_id=9008, site_name="Fort Myers", type="flood", severity="warning",
            title="Flood risk: Caloosahatchee rising after 3.1 in of rain overnight",
            message="Avoid low access roads. River 0.8 ft below action stage.",
            status="active", started_at=now - timedelta(hours=5), all_clear_at=None, cleared_at=None,
            meta={"rain_12h_in": 3.1, "stage_ft": 9.2, "action_stage_ft": 10.0, "gauge_id": "02292900"},
            updated_at=now - timedelta(hours=1),
        ),
    ]


def _reports() -> list[HazardReport]:
    now = _now()
    return [
        HazardReport(
            id=_FIXED_IDS["report-gator"], site_id=9011, latitude=25.623, longitude=-80.476,
            hazard_type="wildlife", severity="high", description="8 ft alligator in the canal next to the laydown yard",
            reporter_name="J. Ramirez", photo_url=None, status="active",
            created_at=now - timedelta(hours=20), expires_at=now + timedelta(hours=28),
        ),
        HazardReport(
            id=_FIXED_IDS["report-mud"], site_id=9001, latitude=25.431, longitude=-80.338,
            hazard_type="unstable_ground", severity="medium", description="Access road soft, truck stuck at mile 2",
            reporter_name="T. Nguyen", photo_url=None, status="active",
            created_at=now - timedelta(hours=3), expires_at=None,
        ),
    ]


def site_summaries() -> list[SiteSummary]:
    alerts = _alerts()
    order = {"danger": 0, "warning": 1, "info": 2}
    out = []
    for sid, name, utility, county, ptype, cap, lat, lon, tz in _SITES:
        site_alerts = sorted([a for a in alerts if a.site_id == sid], key=lambda a: order[a.severity])
        out.append(SiteSummary(
            id=sid, name=name, utility=utility, county=county, plant_type=ptype, capacity_mw=cap,
            latitude=lat, longitude=lon, timezone=tz, risk=_risk(sid),
            active_alert_count=len(site_alerts), top_alert=site_alerts[0].type if site_alerts else None,
            heat_index_f=_conditions(sid, _now().replace(minute=0)).heat_index_f,
        ))
    return sorted(out, key=lambda s: s.risk.score if s.risk else -1, reverse=True)


def site_detail(site_id: int) -> SiteDetail | None:
    summary = next((s for s in site_summaries() if s.id == site_id), None)
    if summary is None:
        return None
    hour = _now().replace(minute=0)
    past = [_conditions(site_id, hour - timedelta(hours=h)) for h in range(24)]
    base = _SCORES[site_id]
    history = [
        RiskPoint(ts=hour + timedelta(hours=h), score=round(min(10, max(0, base + 1.5 * math.sin(h / 4))), 1),
                  level=_level(base), kind="current" if h <= 0 else "forecast")
        for h in range(-24, 25)
    ]
    return SiteDetail(
        site=summary,
        conditions=past[0],
        last_24h=Last24h(
            total_precip_in=round(sum(c.precip_in or 0 for c in past), 2),
            max_heat_index_f=max(c.heat_index_f or 0 for c in past),
            max_gust_mph=max(c.gust_mph or 0 for c in past),
        ),
        forecast=[_conditions(site_id, hour + timedelta(hours=h)) for h in range(1, 49)],
        alerts=[a for a in _alerts() if a.site_id == site_id],
        reports=[r for r in _reports() if r.site_id == site_id],
        risk_history=history,
    )


def alerts(site_id: int | None = None) -> list[Alert]:
    return [a for a in _alerts() if site_id is None or a.site_id == site_id]


def reports(site_id: int | None = None) -> list[HazardReport]:
    return [r for r in _reports() if site_id is None or r.site_id == site_id]


def briefings(for_date: date) -> list[Briefing]:
    out = []
    for s in site_summaries():
        out.append(Briefing(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"planit-mock/briefing/{s.id}/{for_date}"),
            site_id=s.id, site_name=s.name, for_date=for_date,
            summary=(f"Risk {s.risk.score}/10 ({s.risk.level}). Start before 7 AM; heat index peaks near "
                     f"{round(s.heat_index_f or 100)}°F by early afternoon. Storms likely 2-6 PM."),
            details={"peak_heat_index_f": round(s.heat_index_f or 100), "storm_window": "2 PM - 6 PM",
                     "risk_score": s.risk.score,
                     "recommendations": ["Water/rest/shade every hour after 11 AM",
                                         "Lightning plan: vehicles are shelter, not tents"]},
            generated_by="template", generated_at=_now(),
        ))
    return out
