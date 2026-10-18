"""Owner: Person A. Hazard scores (0-10) per site: current hour + next 24 hours -> `hazard_scores`.

Every run writes two scorers side by side, so the dashboard's Real-time / Predictive switch can show either:

- scorer 'rules' (Real-time), rules-v2 (planit/hazards.py): every hazard on one 0-10 scale anchored to published
  work rules (the NWS heat index on OSHA's bands, wind chill, visibility, lightning, forecast thunderstorms and
  storm energy, wind gusts against lift limits, rain rate, 24 h rain, saturated ground, smoke (PM2.5 AQI from
  `air_quality`), fire weather (dry air with wind after 3 dry days), NWS alerts by event, nearby wildfires and felt
  earthquakes (alerts the worker scores). The
  site score is the worst kind of hazard plus a little for other serious ones; each factor carries a recommended
  action. Its weather is the NWS forecast and station observations (`nws_weather`, every 30 min) laid over
  Open-Meteo (merge_weather()), which still supplies soil moisture, CAPE and hourly rain.
- scorer 'ml' (Predictive), with a trained model in ml/models/ and PLANIT_SCORE_MODEL=xgb (the default): the XGBoost
  model scores each hour on the 24 hours around it (the "day" it learned from), on the Real-time scale (a Predictive
  5 is as likely to be a hazard day as a Real-time 5, see ml/model.py), with the OSHA heat floor, plus alert points
  and a floor at the Real-time severity of any NWS warning, lightning, wildfire or earthquake alert in force that
  hour (combine()), and of smoke and fire weather (smoke_floor(), fire_weather_floor()). The floors are per hour, so
  the forecast goes back down when the heat, the warning, the smoke or the dry wind ends.

Rows carry the scorer's version ('rules-v2', 'xgb-2026-10-17').

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

from planit import hazards
from planit.config import settings
from planit.db import connection

log = logging.getLogger(__name__)

MODEL_VERSION = "rules-v2"
FORECAST_HOURS = 24
RULES_HISTORY = timedelta(hours=72)  # rain in the last 3 days, for saturated ground
ML_HALF_WINDOW = timedelta(hours=12)  # each hour is scored on the 24 h around it
ML_RAIN_HISTORY = timedelta(days=3)  # precip_prev_3d_in: the 3 days before that window
NO_SNOW_ABOVE_F = 34.0  # same as features.NO_SNOW_ABOVE_F (features needs pandas; this module mustn't)

# ML scorer only: alert points on top of the model's weather score (see combine()). The floor for an alert in force
# is its own Real-time severity (hazards.alert: lightning 10, Tornado Warning 10, Wind Advisory 4.5, ...).
ALERT_POINTS = {"danger": 2.5, "warning": 1.2, "info": 0.3}
LIGHTNING_POINTS = 4.0


def level_for(score: float) -> str:
    if score >= 7.5:
        return "extreme"
    if score >= 5:
        return "high"
    if score >= 2.5:
        return "moderate"
    return "low"


# --- rules-v2 (scorer 'rules') ------------------------------------------------------------------------------

@dataclass
class HourInputs:
    heat_index_f: float | None = None  # NWS heat index (hazards.nws_heat_index), not Open-Meteo "feels like"
    rain_1h_in: float | None = None
    rain_24h_in: float | None = None
    rain_72h_in: float | None = None
    soil_moisture: float | None = None
    gust_mph: float | None = None
    cape_jkg: float | None = None
    precip_prob_pct: float | None = None
    weather_code: int | None = None
    wind_chill_f: float | None = None
    visibility_m: float | None = None
    snow_1h_in: float | None = None
    snow_24h_in: float | None = None
    ice_24h_in: float | None = None
    us_aqi_pm2_5: float | None = None  # smoke: US AQI for PM2.5 (`air_quality`, Open-Meteo / CAMS)
    humidity_pct: float | None = None  # with gusts and 72 h rain: fire weather
    is_forecast: bool = False
    alerts: list[dict] = field(default_factory=list)  # see alerts_at()


def rule_hazards(x: HourInputs) -> list[hazards.Hazard | None]:
    return [
        hazards.heat(x.heat_index_f),
        hazards.cold(x.wind_chill_f),
        hazards.visibility(x.visibility_m),
        hazards.snow(x.snow_1h_in, x.snow_24h_in),
        hazards.ice(x.ice_24h_in),
        hazards.thunderstorm(x.weather_code, x.is_forecast) or hazards.storm_potential(x.cape_jkg, x.precip_prob_pct),
        hazards.wind(x.gust_mph),
        hazards.rain_rate(x.rain_1h_in),
        hazards.rain_24h(x.rain_24h_in),
        hazards.ground(x.soil_moisture, x.rain_72h_in),
        hazards.smoke(x.us_aqi_pm2_5),
        fire_weather(x),
        *(hazards.alert(a) for a in x.alerts),
    ]


def fire_weather(x: HourInputs) -> hazards.Hazard | None:
    return hazards.fire_weather(x.humidity_pct, x.gust_mph, x.rain_72h_in, x.snow_24h_in)


def score_hour(x: HourInputs) -> tuple[float, list[dict]]:
    """rules-v2 (score, top-3 factors with actions) for one site-hour."""
    return hazards.combine(rule_hazards(x))


def _short_title(alert: dict) -> str:
    meta = alert.get("meta") or {}
    return meta.get("nws_event") or alert["title"]


def _applies(alert: dict, hour: datetime) -> bool:
    """Is this active alert still in force at `hour`? Lightning lasts until all-clear, NWS until it ends."""
    if alert["type"] == "lightning":
        return alert["all_clear_at"] is None or alert["all_clear_at"] > hour
    ends = (alert.get("meta") or {}).get("ends")
    return ends is None or datetime.fromisoformat(ends) > hour


def alerts_at(alerts: list[dict], hour: datetime) -> list[dict]:
    """Active alerts in force at `hour`: {"type", "severity", "title" (short), "nws_event", "nws_severity",
    "nearest_mi", "rule_severity", "action"}, the shape both hazards.alert() and combine() take."""
    out = []
    for a in alerts:
        if not _applies(a, hour):
            continue
        meta = a.get("meta") or {}
        out.append({"type": a["type"], "severity": a["severity"], "title": _short_title(a),
                    "nws_event": meta.get("nws_event"), "nws_severity": meta.get("nws_severity"),
                    "nearest_mi": meta.get("nearest_strike_mi"),
                    # Wildfire and earthquake alerts are scored by hazards.py when they're raised.
                    "rule_severity": meta.get("rule_severity"), "action": meta.get("action")})
    return out


AIR_STALE_AFTER = timedelta(hours=3)  # air_quality is polled every 2 h


def aqi_at(air: list[dict], hour: datetime) -> float | None:
    """US AQI for PM2.5 at `hour`: that hour's row, or the latest one in the 3 h before it."""
    rows = [a for a in air if hour - AIR_STALE_AFTER <= a["ts"] <= hour and a.get("us_aqi_pm2_5") is not None]
    return max(rows, key=lambda a: a["ts"])["us_aqi_pm2_5"] if rows else None


def _total(rows: list[dict], key: str) -> float | None:
    values = [r[key] for r in rows if r.get(key) is not None]
    return sum(values) if values else None


# NWS values that replace Open-Meteo's for the same hour in rules-v2. Rain and snow stay Open-Meteo's when it has the
# hour: NWS gives 6-hour totals, which would smear a 1 in/h downpour into a drizzle. Ice only NWS forecasts.
NWS_OVERRIDES = ("temp_f", "humidity_pct", "wind_mph", "gust_mph", "precip_prob_pct", "weather_code",
                 "wind_chill_f", "visibility_m", "ice_in")
NWS_FALLBACKS = ("precip_in", "snowfall_in")
WEATHER_KEYS = ("temp_f", "humidity_pct", "heat_index_f", "precip_in", "precip_prob_pct", "soil_moisture",
                "wind_mph", "gust_mph", "cape_jkg", "weather_code", "wind_chill_f", "visibility_m", "snowfall_in",
                "ice_in")


def merge_weather(open_meteo: list[dict], nws: list[dict]) -> list[dict]:
    """rules-v2 weather for one site: Open-Meteo rows with NWS readings laid over them hour by hour (an NWS value
    wins when it isn't null). Hours only NWS has take its rain and Open-Meteo's latest soil moisture before them."""
    by_ts = {w["ts"]: {k: w.get(k) for k in WEATHER_KEYS} | {"ts": w["ts"]} for w in open_meteo}
    for n in nws:
        row = by_ts.setdefault(n["ts"], dict.fromkeys(WEATHER_KEYS) | {"ts": n["ts"]})
        for key in NWS_OVERRIDES:
            if n.get(key) is not None:
                row[key] = n[key]
        for key in NWS_FALLBACKS:
            if row[key] is None:
                row[key] = n.get(key)
    rows = sorted(by_ts.values(), key=lambda r: r["ts"])
    soil = None
    for r in rows:
        soil = r["soil_moisture"] = r["soil_moisture"] if r["soil_moisture"] is not None else soil
    return rows


def build_inputs(weather: list[dict], alerts: list[dict], hours: list[datetime],
                 air: list[dict] | None = None) -> dict[datetime, HourInputs]:
    """Per-hour rules-v2 inputs for one site. `weather` (and `air`, air_quality rows) are observed up to now and
    forecast after; hours[0] is now."""
    by_hour = {w["ts"]: w for w in weather}
    out = {}
    for hour in hours:
        row = by_hour.get(hour)
        if row is None:  # no reading for this exact hour: use the latest one before it
            earlier = [w for w in weather if w["ts"] <= hour]
            row = earlier[-1] if earlier else None
        if row is None:
            continue
        last_24h = [w for w in weather if hour - timedelta(hours=24) < w["ts"] <= hour]
        out[hour] = HourInputs(
            heat_index_f=hazards.nws_heat_index(row["temp_f"], row["humidity_pct"]),
            rain_1h_in=row["precip_in"],
            rain_24h_in=_total(last_24h, "precip_in"),
            rain_72h_in=_total([w for w in weather if hour - RULES_HISTORY < w["ts"] <= hour], "precip_in"),
            soil_moisture=row["soil_moisture"], gust_mph=row["gust_mph"], cape_jkg=row["cape_jkg"],
            precip_prob_pct=row["precip_prob_pct"], weather_code=row["weather_code"],
            wind_chill_f=(row["wind_chill_f"] if row.get("wind_chill_f") is not None
                          else hazards.wind_chill_f(row["temp_f"], row.get("wind_mph"))),
            visibility_m=row.get("visibility_m"),
            snow_1h_in=row.get("snowfall_in"),
            snow_24h_in=_total(last_24h, "snowfall_in"),
            ice_24h_in=_total(last_24h, "ice_in"),
            us_aqi_pm2_5=aqi_at(air or [], hour),
            humidity_pct=row["humidity_pct"],
            is_forecast=hour > hours[0], alerts=alerts_at(alerts, hour),
        )
    return out


# --- ML model (scorer 'ml') ---------------------------------------------------------------------------------

def combine(weather_score: float, weather_factors: list[dict], alerts: list[dict]) -> tuple[float, list[dict]]:
    """ML scorer: the model's weather score + alert points, capped at 10, and never below the Real-time severity of
    an alert in force at this hour (Wind Advisory 4.5, Heat Advisory 5, lightning 10, ...: `alerts` are the ones that
    apply to this hour, see alerts_at(), so the floor lifts when the warning ends)."""
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
    if alerts:
        worst = max(alerts, key=lambda a: hazards.alert(a).severity)
        floor = hazards.alert(worst).severity  # the Real-time score of the alert itself
        if floor > score:
            key = f"alert_{worst['type']}"
            factor = next((f for f in extra if f["key"] == key), None)
            if factor is None:
                label = "Lightning within 10 miles" if worst["type"] == "lightning" else worst["title"]
                factor = {"key": key, "label": label, "contribution": 0.0}
                extra.append(factor)
            factor["contribution"] = round(factor["contribution"] + floor - score, 1)
            score = floor
    factors = sorted([*weather_factors, *extra], key=lambda f: f["contribution"], reverse=True)
    return round(score, 1), factors[:3]


def rule_floor(score: float, factors: list[dict], hazard: hazards.Hazard | None) -> tuple[float, list[dict]]:
    """ML scorer: never below a Real-time hazard the model can't weigh at this hour; it takes up the difference."""
    if hazard is None or hazard.severity <= score:
        return score, factors
    factor = {"key": hazard.key, "label": hazard.label, "contribution": round(hazard.severity - score, 1),
              "action": hazard.action}
    return round(hazard.severity, 1), sorted([*factors, factor], key=lambda f: f["contribution"], reverse=True)[:3]


def smoke_floor(score: float, factors: list[dict], us_aqi_pm2_5: float | None) -> tuple[float, list[dict]]:
    """Never below the Real-time smoke severity. The model has never seen air quality, so like the OSHA heat floor
    this keeps Predictive from calling a smoky day calm."""
    return rule_floor(score, factors, hazards.smoke(us_aqi_pm2_5))


def fire_weather_floor(score: float, factors: list[dict], x: HourInputs | None) -> tuple[float, list[dict]]:
    """Never below the Real-time fire weather severity: NOAA rarely logs a dry, gusty day as a hazard day, so the
    model learned to call them calm, though a spark from hot work spreads fastest then."""
    return rule_floor(score, factors, fire_weather(x) if x else None)


def window_features(weather: list[dict], hour: datetime, site: dict | None = None) -> dict | None:
    """The ML model's features for one site-hour, from the 24 h around it (same columns as features.FEATURES).
    `site` gives latitude and longitude."""
    start, end = hour - ML_HALF_WINDOW, hour + ML_HALF_WINDOW
    window = [w for w in weather if start <= w["ts"] < end]
    if not window:
        return None

    def values(key: str, rows: list[dict]) -> list[float]:
        return [r[key] for r in rows if r.get(key) is not None]

    heat, rain, soil, gust = (values(k, window) for k in ("heat_index_f", "precip_in", "soil_moisture", "gust_mph"))
    temps, snow, depth, humidity = (values(k, window) for k in ("temp_f", "snowfall_in", "snow_depth_ft",
                                                                "humidity_pct"))
    chills = [c for w in window if (c := hazards.wind_chill_f(w.get("temp_f"), w.get("wind_mph"))) is not None]
    before = values("precip_in", [w for w in weather if start - ML_RAIN_HISTORY <= w["ts"] < start])
    min_temp = min(temps, default=None)
    no_snow = 0.0 if min_temp is not None and min_temp > NO_SNOW_ABOVE_F else None  # as features.add_features()
    return {
        "max_heat_index_f": max(heat, default=None),
        "total_precip_in": sum(rain) if rain else None,
        "precip_prev_3d_in": sum(before) if before else None,
        "avg_soil_moisture": mean(soil) if soil else None,
        "max_gust_mph": max(gust, default=None),
        "max_hourly_precip_in": max(rain, default=None),
        "month": hour.month,
        "min_temp_f": min_temp,
        "min_wind_chill_f": min(chills, default=None),
        "total_snowfall_in": sum(snow) if snow else no_snow,
        "max_snow_depth_ft": max(depth) if depth else no_snow,
        "min_humidity_pct": min(humidity, default=None),
        "latitude": site["latitude"] if site else None,
        "longitude": site["longitude"] if site else None,
    }


@functools.cache
def ml_model():
    """The latest trained model, or None (then only rules-v2 scores are written) if disabled, missing or not
    installed."""
    if settings.score_model != "xgb":
        return None
    try:
        from planit.ml.model import load_latest  # pandas + xgboost: the [ml] extras
        return load_latest()
    except (ImportError, FileNotFoundError) as e:
        log.warning("ML model unavailable (%s); writing %s scores only", e, MODEL_VERSION)
        return None


def ml_scores(model, weather: list[dict], alerts: list[dict], hours: list[datetime],
              site: dict | None = None, air: list[dict] | None = None) -> dict[datetime, tuple]:
    """(score, factors) per hour from the ML model, plus alert points, the alert floor, and the smoke and fire
    weather floors (from this hour's Open-Meteo readings, the source the model sees)."""
    import pandas as pd

    rows = [(hour, f) for hour in hours if (f := window_features(weather, hour, site)) is not None]
    if not rows:
        return {}
    frame = pd.DataFrame([f for _, f in rows], columns=model.features).astype(float)
    inputs = build_inputs(weather, [], hours, air)
    out = {}
    for (hour, _), (score, factors) in zip(rows, model.explain(frame), strict=True):
        scored = smoke_floor(*combine(score, factors, alerts_at(alerts, hour)), aqi_at(air or [], hour))
        out[hour] = fire_weather_floor(*scored, inputs.get(hour))
    return out


# --- Writing ------------------------------------------------------------------------------------------------

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
    """hazard_scores rows for every site, current hour + next 24, without writing them: rules-v2 always
    (scorer 'rules'), plus the ML model (scorer 'ml') when one is enabled, so the dashboard can switch."""
    now = datetime.now(UTC)
    current = now.replace(minute=0, second=0, microsecond=0)
    hours = [current + timedelta(hours=h) for h in range(FORECAST_HOURS + 1)]

    model = ml_model()
    # Observed rows up to now, forecast rows after. rules-v2 looks 3 days back (rain for saturated ground); the
    # model 12 h either side of each hour plus 3 days of rain before that.
    first = current - (ML_HALF_WINDOW + ML_RAIN_HISTORY if model else RULES_HISTORY)
    last = hours[-1] + (ML_HALF_WINDOW if model else timedelta(0))
    with connection() as conn:
        weather = conn.execute(
            "SELECT site_id, ts, temp_f, humidity_pct, heat_index_f, precip_in, precip_prob_pct, soil_moisture, "
            "wind_mph, gust_mph, cape_jkg, weather_code, snowfall_in, snow_depth_ft FROM weather "
            "WHERE ts > %s AND ts <= %s "
            "AND ((NOT is_forecast AND ts <= %s) OR (is_forecast AND ts > %s)) ORDER BY site_id, ts",
            (first, last, now, now),
        ).fetchall()
        sites = {s["id"]: s for s in conn.execute("SELECT id, latitude, longitude FROM sites").fetchall()}
        nws = conn.execute(
            "SELECT site_id, ts, temp_f, humidity_pct, precip_in, precip_prob_pct, wind_mph, gust_mph, weather_code, "
            "wind_chill_f, visibility_m, snowfall_in, ice_in FROM nws_weather WHERE ts > %s AND ts <= %s "
            "AND ((NOT is_forecast AND ts <= %s) OR (is_forecast AND ts > %s)) ORDER BY site_id, ts",
            (current - RULES_HISTORY, hours[-1], now, now),
        ).fetchall()
        alerts = conn.execute(
            "SELECT site_id, type, severity, title, all_clear_at, meta FROM alerts WHERE status = 'active'"
        ).fetchall()
        air = conn.execute(
            "SELECT site_id, ts, us_aqi_pm2_5 FROM air_quality WHERE ts > %s AND ts <= %s "
            "AND ((NOT is_forecast AND ts <= %s) OR (is_forecast AND ts > %s)) ORDER BY site_id, ts",
            (current - AIR_STALE_AFTER, hours[-1], now, now),
        ).fetchall()

    weather_by_site: dict[int, list[dict]] = defaultdict(list)
    for w in weather:
        weather_by_site[w["site_id"]].append(w)
    nws_by_site: dict[int, list[dict]] = defaultdict(list)
    for n in nws:
        nws_by_site[n["site_id"]].append(n)
    alerts_by_site: dict[int, list[dict]] = defaultdict(list)
    for a in alerts:
        alerts_by_site[a["site_id"]].append(a)
    air_by_site: dict[int, list[dict]] = defaultdict(list)
    for a in air:
        air_by_site[a["site_id"]].append(a)

    rows = []
    for site_id in weather_by_site.keys() | nws_by_site.keys():
        site_weather, site_alerts, site_air = weather_by_site[site_id], alerts_by_site[site_id], air_by_site[site_id]
        # Real-time: NWS readings over Open-Meteo. Predictive: Open-Meteo only, the source the model was trained on.
        rules_weather = merge_weather(site_weather, nws_by_site[site_id])
        scorers = [("rules", MODEL_VERSION,
                    {h: score_hour(x) for h, x in build_inputs(rules_weather, site_alerts, hours, site_air).items()})]
        if model:
            scorers.append(("ml", model.version, ml_scores(model, site_weather, site_alerts, hours,
                                                           sites.get(site_id), site_air)))
        for scorer, version, scored in scorers:
            for hour, (score, factors) in scored.items():
                rows.append({"site_id": site_id, "ts": hour, "kind": "current" if hour == current else "forecast",
                             "scorer": scorer, "score": score, "level": level_for(score), "factors": Jsonb(factors),
                             "model_version": version})
    return rows
