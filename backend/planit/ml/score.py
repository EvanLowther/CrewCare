"""Owner: Person A. Hazard score (0-10) per site: current hour + next 24 hours -> `hazard_scores`.

rules-v1 is a transparent rule-based score so the dashboard has real scores before the ML model
exists. Each factor adds points; its label states the fact behind it (supervisors read these):

    heat index    up to 3.5  0 below 90°F, 1.5 at 103°F (OSHA "extreme caution"), 3.0 at 115°F, 3.5 above
    thunderstorm  up to 2.5  2.5 when storms are forecast (WMO 95-99), else CAPE x rain chance
    24 h rain     up to 2    ~0.7 per inch
    wet ground    up to 1.5  soil moisture 25% -> 40%
    wind gusts    up to 2    0 below 25 mph, 1.5 at 45 mph, 2 above
    alerts        up to 4    lightning 4, danger 2.5, warning 1.2, info 0.3; strongest + half the next

The total is capped at 10, and an active lightning stop-work alert keeps the score at least 8.
When the XGBoost model lands it writes the same rows with a different model_version.

Level bands (keep in sync with frontend/src/lib/risk.ts): low < 2.5 <= moderate < 5 <= high < 7.5 <= extreme
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from planit.db import connection

log = logging.getLogger(__name__)

MODEL_VERSION = "rules-v1"
FORECAST_HOURS = 24
LIGHTNING_FLOOR = 8.0
ALERT_POINTS = {"danger": 2.5, "warning": 1.2, "info": 0.3}
LIGHTNING_POINTS = 4.0
THUNDERSTORM_CODES = range(95, 100)


def level_for(score: float) -> str:
    if score >= 7.5:
        return "extreme"
    if score >= 5:
        return "high"
    if score >= 2.5:
        return "moderate"
    return "low"


@dataclass
class HourInputs:
    heat_index_f: float | None = None
    rain_24h_in: float | None = None
    soil_moisture: float | None = None
    gust_mph: float | None = None
    cape_jkg: float | None = None
    precip_prob_pct: float | None = None
    weather_code: int | None = None
    alerts: list[dict] = field(default_factory=list)  # {"type", "severity", "title"}


def _ramp(value: float, start: float, end: float, points: float) -> float:
    """0 at `start`, `points` at `end`, linear between."""
    if value <= start:
        return 0.0
    return points * min(1.0, (value - start) / (end - start))


def heat_points(hi: float) -> float:
    if hi < 90:
        return 0.0
    if hi < 103:
        return _ramp(hi, 90, 103, 1.5)
    if hi < 115:
        return 1.5 + _ramp(hi, 103, 115, 1.5)
    return 3.5


def storm_points(code: int | None, cape: float | None, prob: float | None) -> float:
    if code is not None and code in THUNDERSTORM_CODES:
        return 2.5
    if cape is None:
        return 0.0
    chance = (prob / 100) if prob is not None else 0.5
    return round(_ramp(cape, 1000, 3000, 2.0) * chance, 3)


def score_hour(x: HourInputs) -> tuple[float, list[dict]]:
    """(score, top-3 factors) for one site-hour."""
    factors: list[dict] = []

    def add(key: str, label: str, points: float) -> None:
        if points >= 0.05:
            factors.append({"key": key, "label": label, "contribution": round(points, 1)})

    if x.heat_index_f is not None:
        add("heat_index", f"Heat index {round(x.heat_index_f)}°F", heat_points(x.heat_index_f))
    storms = storm_points(x.weather_code, x.cape_jkg, x.precip_prob_pct)
    if x.weather_code in THUNDERSTORM_CODES:
        add("thunderstorm", "Thunderstorms forecast", storms)
    elif storms:
        chance = f", {round(x.precip_prob_pct)}% rain chance" if x.precip_prob_pct is not None else ""
        add("thunderstorm", f"Storm energy (CAPE {round(x.cape_jkg):,}{chance})", storms)
    if x.rain_24h_in is not None:
        add("rain_24h", f"{x.rain_24h_in:.1f} in of rain in 24 h", min(2.0, x.rain_24h_in * 0.7))
    if x.soil_moisture is not None:
        add("soil_moisture", f"Wet ground (soil moisture {round(x.soil_moisture * 100)}%)",
            _ramp(x.soil_moisture, 0.25, 0.40, 1.5))
    if x.gust_mph is not None:
        gust = 2.0 if x.gust_mph > 45 else _ramp(x.gust_mph, 25, 45, 1.5)
        add("wind", f"Gusts {round(x.gust_mph)} mph", gust)

    lightning = any(a["type"] == "lightning" for a in x.alerts)
    alert_pts = sorted(
        ((LIGHTNING_POINTS if a["type"] == "lightning" else ALERT_POINTS.get(a["severity"], 0.0), a)
         for a in x.alerts),
        key=lambda p: p[0], reverse=True,
    )
    for i, (points, alert) in enumerate(alert_pts[:2]):
        label = "Lightning within 10 miles" if alert["type"] == "lightning" else alert["title"]
        add(f"alert_{alert['type']}", label, points if i == 0 else points / 2)

    score = min(10.0, sum(f["contribution"] for f in factors))
    if lightning:
        score = max(score, LIGHTNING_FLOOR)
    factors.sort(key=lambda f: f["contribution"], reverse=True)
    return round(score, 1), factors[:3]


def _short_title(alert: dict) -> str:
    meta = alert.get("meta") or {}
    return meta.get("nws_event") or alert["title"]


def _applies(alert: dict, hour: datetime) -> bool:
    """Is this active alert still in force at `hour`? Lightning lasts until all-clear, NWS until it ends."""
    if alert["type"] == "lightning":
        return alert["all_clear_at"] is None or alert["all_clear_at"] > hour
    ends = (alert.get("meta") or {}).get("ends")
    return ends is None or datetime.fromisoformat(ends) > hour


def build_inputs(weather: list[dict], alerts: list[dict], hours: list[datetime]) -> dict[datetime, HourInputs]:
    """Per-hour inputs for one site. `weather` rows are observed up to now and forecast after."""
    by_hour = {w["ts"]: w for w in weather}
    out = {}
    for hour in hours:
        row = by_hour.get(hour)
        if row is None:  # no reading for this exact hour: use the latest one before it
            earlier = [w for w in weather if w["ts"] <= hour]
            row = earlier[-1] if earlier else None
        if row is None:
            continue
        window = [w["precip_in"] for w in weather if hour - timedelta(hours=24) < w["ts"] <= hour
                  and w["precip_in"] is not None]
        out[hour] = HourInputs(
            heat_index_f=row["heat_index_f"], rain_24h_in=sum(window) if window else None,
            soil_moisture=row["soil_moisture"], gust_mph=row["gust_mph"], cape_jkg=row["cape_jkg"],
            precip_prob_pct=row["precip_prob_pct"], weather_code=row["weather_code"],
            alerts=[{"type": a["type"], "severity": a["severity"], "title": _short_title(a)}
                    for a in alerts if _applies(a, hour)],
        )
    return out


UPSERT_SQL = """
INSERT INTO hazard_scores (site_id, ts, kind, score, level, factors, model_version, computed_at)
VALUES (%(site_id)s, %(ts)s, %(kind)s, %(score)s, %(level)s, %(factors)s, %(model_version)s, now())
ON CONFLICT (site_id, ts, kind) DO UPDATE SET
    score = EXCLUDED.score, level = EXCLUDED.level, factors = EXCLUDED.factors,
    model_version = EXCLUDED.model_version, computed_at = now()
"""


def score_all() -> int:
    """Score every site for the current hour and the next 24. Returns rows written."""
    now = datetime.now(UTC)
    current = now.replace(minute=0, second=0, microsecond=0)
    hours = [current + timedelta(hours=h) for h in range(FORECAST_HOURS + 1)]

    with connection() as conn:
        # Observed rows up to now, forecast rows after; 24 h of history for the rain window.
        weather = conn.execute(
            "SELECT site_id, ts, heat_index_f, precip_in, precip_prob_pct, soil_moisture, gust_mph, cape_jkg, "
            "weather_code FROM weather WHERE ts > %s AND ts <= %s "
            "AND ((NOT is_forecast AND ts <= %s) OR (is_forecast AND ts > %s)) ORDER BY site_id, ts",
            (current - timedelta(hours=24), hours[-1], now, now),
        ).fetchall()
        alerts = conn.execute(
            "SELECT site_id, type, severity, title, all_clear_at, meta FROM alerts WHERE status = 'active'"
        ).fetchall()

    weather_by_site: dict[int, list[dict]] = defaultdict(list)
    for w in weather:
        weather_by_site[w["site_id"]].append(w)
    alerts_by_site: dict[int, list[dict]] = defaultdict(list)
    for a in alerts:
        alerts_by_site[a["site_id"]].append(a)

    rows = []
    for site_id, site_weather in weather_by_site.items():
        for hour, inputs in build_inputs(site_weather, alerts_by_site[site_id], hours).items():
            score, factors = score_hour(inputs)
            rows.append({"site_id": site_id, "ts": hour, "kind": "current" if hour == current else "forecast",
                         "score": score, "level": level_for(score), "factors": Jsonb(factors),
                         "model_version": MODEL_VERSION})

    with connection() as conn, conn.transaction(), conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, rows)
    log.info("scored %d sites, %d rows", len(weather_by_site), len(rows))
    return len(rows)
