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

With a trained model in ml/models/ (and PLANIT_SCORE_MODEL=xgb, the default), every run also writes ML scores
(scorer 'ml') next to the rules-v1 ones (scorer 'rules'), so the dashboard can switch between them. The ML weather
part comes from the XGBoost model: each hour is scored on the 24 hours around it (12 h back, 12 h ahead), the "day"
the model learned from, with the OSHA heat floor from ml/model.py. Alert points and the lightning floor are added
the same way as above. Rows carry the scorer's version (e.g. 'xgb-2026-10-17').

Level bands (keep in sync with frontend/src/lib/risk.ts): low < 2.5 <= moderate < 5 <= high < 7.5 <= extreme
"""

from __future__ import annotations

import functools
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from statistics import mean

from psycopg.types.json import Jsonb

from planit.config import settings
from planit.db import connection

log = logging.getLogger(__name__)

MODEL_VERSION = "rules-v1"
FORECAST_HOURS = 24
ML_HALF_WINDOW = timedelta(hours=12)  # each hour is scored on the 24 h around it
ML_RAIN_HISTORY = timedelta(days=3)  # precip_prev_3d_in: the 3 days before that window
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

    return combine(sum(f["contribution"] for f in factors), factors, x.alerts)


def combine(weather_score: float, weather_factors: list[dict], alerts: list[dict]) -> tuple[float, list[dict]]:
    """Weather score (rules-v1 or the ML model) + alert points, capped at 10; lightning keeps it at least 8."""
    alert_pts = sorted(
        ((LIGHTNING_POINTS if a["type"] == "lightning" else ALERT_POINTS.get(a["severity"], 0.0), a) for a in alerts),
        key=lambda p: p[0], reverse=True,
    )
    extra = []
    for i, (points, alert) in enumerate(alert_pts[:2]):
        points = points if i == 0 else points / 2
        if points >= 0.05:
            label = "Lightning within 10 miles" if alert["type"] == "lightning" else alert["title"]
            extra.append({"key": f"alert_{alert['type']}", "label": label, "contribution": round(points, 1)})

    score = min(10.0, weather_score + sum(f["contribution"] for f in extra))
    if any(a["type"] == "lightning" for a in alerts):
        score = max(score, LIGHTNING_FLOOR)
    factors = sorted([*weather_factors, *extra], key=lambda f: f["contribution"], reverse=True)
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
            alerts=alerts_at(alerts, hour),
        )
    return out


def alerts_at(alerts: list[dict], hour: datetime) -> list[dict]:
    return [{"type": a["type"], "severity": a["severity"], "title": _short_title(a)}
            for a in alerts if _applies(a, hour)]


def window_features(weather: list[dict], hour: datetime) -> dict | None:
    """The ML model's features for one site-hour, from the 24 h around it (same columns as features.FEATURES)."""
    start, end = hour - ML_HALF_WINDOW, hour + ML_HALF_WINDOW
    window = [w for w in weather if start <= w["ts"] < end]
    if not window:
        return None

    def values(key: str, rows: list[dict]) -> list[float]:
        return [r[key] for r in rows if r[key] is not None]

    heat, rain, soil, gust = (values(k, window) for k in ("heat_index_f", "precip_in", "soil_moisture", "gust_mph"))
    before = values("precip_in", [w for w in weather if start - ML_RAIN_HISTORY <= w["ts"] < start])
    return {
        "max_heat_index_f": max(heat, default=None),
        "total_precip_in": sum(rain) if rain else None,
        "precip_prev_3d_in": sum(before) if before else None,
        "avg_soil_moisture": mean(soil) if soil else None,
        "max_gust_mph": max(gust, default=None),
        "max_hourly_precip_in": max(rain, default=None),
        "month": hour.month,
    }


@functools.cache
def ml_model():
    """The latest trained model, or None (then rules-v1 scores) if disabled, missing or not installed."""
    if settings.score_model != "xgb":
        return None
    try:
        from planit.ml.model import load_latest  # pandas + xgboost: the [ml] extras
        return load_latest()
    except (ImportError, FileNotFoundError) as e:
        log.warning("ML model unavailable (%s); scoring with %s", e, MODEL_VERSION)
        return None


def ml_scores(model, weather: list[dict], alerts: list[dict], hours: list[datetime]) -> dict[datetime, tuple]:
    """(score, factors) per hour from the ML model, plus alert points and the lightning floor."""
    import pandas as pd

    rows = [(hour, f) for hour in hours if (f := window_features(weather, hour)) is not None]
    if not rows:
        return {}
    frame = pd.DataFrame([f for _, f in rows], columns=model.features).astype(float)
    return {hour: combine(score, factors, alerts_at(alerts, hour))
            for (hour, _), (score, factors) in zip(rows, model.explain(frame), strict=True)}


UPSERT_SQL = """
INSERT INTO hazard_scores (site_id, ts, kind, scorer, score, level, factors, model_version, computed_at)
VALUES (%(site_id)s, %(ts)s, %(kind)s, %(scorer)s, %(score)s, %(level)s, %(factors)s, %(model_version)s, now())
ON CONFLICT (site_id, ts, kind, scorer) DO UPDATE SET
    score = EXCLUDED.score, level = EXCLUDED.level, factors = EXCLUDED.factors,
    model_version = EXCLUDED.model_version, computed_at = now()
"""


def score_all() -> int:
    """Score every site for the current hour and the next 24. Returns rows written."""
    rows = compute_scores()
    with connection() as conn, conn.transaction(), conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, rows)
    log.info("scored %d sites, %d rows with %s", len({r["site_id"] for r in rows}), len(rows),
             ", ".join(sorted({r["model_version"] for r in rows})) or "-")
    return len(rows)


def compute_scores() -> list[dict]:
    """hazard_scores rows for every site, current hour + next 24, without writing them: rules-v1 always
    (scorer 'rules'), plus the ML model (scorer 'ml') when one is enabled, so the dashboard can switch."""
    now = datetime.now(UTC)
    current = now.replace(minute=0, second=0, microsecond=0)
    hours = [current + timedelta(hours=h) for h in range(FORECAST_HOURS + 1)]

    model = ml_model()
    # Observed rows up to now, forecast rows after. rules-v1 looks 24 h back; the model 12 h either side of each
    # hour plus 3 days of rain before that.
    first, last = ((current - ML_HALF_WINDOW - ML_RAIN_HISTORY, hours[-1] + ML_HALF_WINDOW) if model
                   else (current - timedelta(hours=24), hours[-1]))
    with connection() as conn:
        weather = conn.execute(
            "SELECT site_id, ts, heat_index_f, precip_in, precip_prob_pct, soil_moisture, gust_mph, cape_jkg, "
            "weather_code FROM weather WHERE ts > %s AND ts <= %s "
            "AND ((NOT is_forecast AND ts <= %s) OR (is_forecast AND ts > %s)) ORDER BY site_id, ts",
            (first, last, now, now),
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
        site_alerts = alerts_by_site[site_id]
        scorers = [("rules", MODEL_VERSION,
                    {h: score_hour(x) for h, x in build_inputs(site_weather, site_alerts, hours).items()})]
        if model:
            scorers.append(("ml", model.version, ml_scores(model, site_weather, site_alerts, hours)))
        for scorer, version, scored in scorers:
            for hour, (score, factors) in scored.items():
                rows.append({"site_id": site_id, "ts": hour, "kind": "current" if hour == current else "forecast",
                             "scorer": scorer, "score": score, "level": level_for(score), "factors": Jsonb(factors),
                             "model_version": version})
    return rows
