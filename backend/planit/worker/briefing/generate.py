"""Owner: Person A. The 6 PM next-day safety briefing, one per site, stored in `briefings`.

At 6 PM in each site's own timezone (sites.timezone), run_due() writes tomorrow's briefing; it runs every 5 minutes,
so a site that's past 6 PM without one (the worker was down, say) still gets it that evening. generate_all() does every
site now (the "Generate now" button, through job_requests).

A briefing covers tomorrow's work day, 6 AM - 6 PM local. Its facts (`details`) come from what's already stored: the
hourly hazard scores for those hours (both scorers; the Real-time factors carry the recommended actions), the NWS and
Open-Meteo forecasts (peak heat index, gusts, rain, snow, ice, wind chill, thunderstorm hours), the smoke forecast
(`air_quality`) and alerts that run into the day (NWS warnings, nearby wildfires, felt earthquakes). `summary` is a
short paragraph: Gemini writes it from those facts in batches of BATCH sites (a few calls a day, inside the free
tier), and any site Gemini doesn't return cleanly gets the template instead (generated_by 'template'). With no
PLANIT_GEMINI_API_KEY every briefing is the template.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime, time, timedelta
from time import sleep
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from planit import hazards
from planit.config import settings
from planit.db import connection
from planit.ml.score import level_for
from planit.worker import jobs

log = logging.getLogger(__name__)

BRIEFING_HOUR = 18  # 6 PM site-local
WORK_START, WORK_END = 6, 18  # the hours briefed, site-local
BATCH = 20  # sites per Gemini request
MAX_SUMMARY_CHARS = 600
RETRY_ON = (429, 500, 503)  # busy or rate-limited: wait and try the same model once more
RETRY_WAIT_S = 8
THUNDER_LIKELY_PCT = 40
SMOKE_MENTION_AQI = 101  # PM2.5 AQI from which smoke counts (hazards.SMOKE_ANCHORS)


# --- When ---------------------------------------------------------------------------------------------------

def next_work_day(now: datetime, tz: str) -> date:
    return now.astimezone(ZoneInfo(tz)).date() + timedelta(days=1)


def is_due(now: datetime, tz: str) -> bool:
    """Past 6 PM site-local (tomorrow's briefing is due until midnight)."""
    return now.astimezone(ZoneInfo(tz)).hour >= BRIEFING_HOUR


def work_window(day: date, tz: str) -> tuple[datetime, datetime]:
    """[start, end) of the briefed work day in UTC."""
    zone = ZoneInfo(tz)
    start = datetime.combine(day, time(WORK_START), zone)
    return start.astimezone(UTC), datetime.combine(day, time(WORK_END), zone).astimezone(UTC)


def _clock(ts: datetime, tz: str) -> str:
    return ts.astimezone(ZoneInfo(tz)).strftime("%I %p").lstrip("0")


# --- Facts --------------------------------------------------------------------------------------------------

def _hour_weather(nws: list[dict], open_meteo: list[dict]) -> list[dict]:
    """One row per forecast hour: NWS values where it has them, Open-Meteo filling the gaps."""
    by_ts: dict[datetime, dict] = {w["ts"]: dict(w) for w in open_meteo}
    for n in nws:
        row = by_ts.setdefault(n["ts"], {"ts": n["ts"]})
        row.update({k: v for k, v in n.items() if v is not None})
    return [by_ts[ts] for ts in sorted(by_ts)]


def _storm_window(hours: list[dict], tz: str) -> str | None:
    stormy = [h["ts"] for h in hours
              if (h.get("weather_code") or 0) >= 95 or (h.get("thunder_prob_pct") or 0) >= THUNDER_LIKELY_PCT]
    if not stormy:
        return None
    return f"{_clock(min(stormy), tz)} - {_clock(max(stormy) + timedelta(hours=1), tz)}"


def _peak(hours: list[dict], key: str, lowest: bool = False) -> tuple[float | None, datetime | None]:
    values = [(h[key], h["ts"]) for h in hours if h.get(key) is not None]
    if not values:
        return None, None
    value, ts = (min if lowest else max)(values, key=lambda v: v[0])
    return round(float(value), 1), ts


def _total(hours: list[dict], key: str) -> float | None:
    values = [h[key] for h in hours if h.get(key) is not None]
    return round(float(sum(values)), 2) if values else None


def _alert_name_and_action(a: dict) -> tuple[str, str | None]:
    """An alert in force tomorrow: its NWS event name and the rules-v2 action, or for alerts the worker scored when
    it raised them (wildfire, earthquake) their title and stored action."""
    meta = a.get("meta") or {}
    if meta.get("nws_event"):
        action = hazards.nws_event(meta["nws_event"])[1]
        return meta["nws_event"], None if action == "Check the NWS alert for details" else action
    return a["title"], meta.get("action")


def build_facts(scores: list[dict], nws: list[dict], open_meteo: list[dict], alerts: list[dict], tz: str,
                air: list[dict] | None = None) -> dict:
    """The `details` of one site's briefing from its rows for the work day (all already limited to the window)."""
    by_scorer = {s: [r for r in scores if r["scorer"] == s] for s in ("ml", "rules")}
    predictive = max((float(r["score"]) for r in by_scorer["ml"]), default=None)
    real_time = max((float(r["score"]) for r in by_scorer["rules"]), default=None)
    top = predictive if predictive is not None else real_time

    hours = _hour_weather(nws, open_meteo)
    for h in hours:
        h["nws_heat_index_f"] = hazards.nws_heat_index(h.get("temp_f"), h.get("humidity_pct"))
        if h.get("wind_chill_f") is None and h.get("temp_f") is not None:
            h["wind_chill_f"] = hazards.wind_chill_f(h["temp_f"], h.get("wind_mph"))
    heat, heat_at = _peak(hours, "nws_heat_index_f")
    chill, _ = _peak(hours, "wind_chill_f", lowest=True)
    gust, gust_at = _peak(hours, "gust_mph")
    smoke, smoke_at = _peak(air or [], "us_aqi_pm2_5")

    # The worst moment of each Real-time hazard during the day, with its action.
    worst: dict[str, dict] = {}
    for r in by_scorer["rules"]:
        for f in r["factors"] or []:
            if f["key"] not in worst or f["contribution"] > worst[f["key"]]["contribution"]:
                worst[f["key"]] = f
    top_hazards = sorted((f for f in worst.values() if f["contribution"] >= 2.5),
                         key=lambda f: f["contribution"], reverse=True)[:3]

    named = sorted({_alert_name_and_action(a) for a in alerts}, key=lambda p: p[0])
    recommendations: list[str] = []
    if heat is not None and heat >= 103:
        recommendations.append("Start early; enforce water, rest and shade every hour after 11 AM")
    smoke_hazard = hazards.smoke(smoke) if smoke is not None and smoke >= SMOKE_MENTION_AQI else None
    actions = [f.get("action") for f in top_hazards] + [action for _, action in named]
    actions += [smoke_hazard.action] if smoke_hazard else []
    for action in actions:
        if action and action not in recommendations:
            recommendations.append(action)

    return {
        "risk_score": top,
        "level": None if top is None else level_for(top),
        "predictive_score": predictive,
        "real_time_peak": real_time,
        "peak_heat_index_f": None if heat is None else round(heat),
        "peak_heat_time": _clock(heat_at, tz) if heat_at and heat is not None and heat >= 90 else None,
        "max_gust_mph": None if gust is None else round(gust),
        "max_gust_time": _clock(gust_at, tz) if gust_at else None,
        "rain_in": _total(hours, "precip_in"),
        "snowfall_in": _total(hours, "snowfall_in"),
        "ice_in": _total(hours, "ice_in"),
        "min_wind_chill_f": None if chill is None or chill > 32 else round(chill),
        "storm_window": _storm_window(hours, tz),
        "peak_smoke_aqi": None if smoke_hazard is None else round(smoke),
        "peak_smoke_time": _clock(smoke_at, tz) if smoke_hazard and smoke_at else None,
        "nws_alerts": [name for name, _ in named],
        "top_hazards": [f["label"] for f in top_hazards],
        "recommendations": recommendations[:4],
    }


# --- Words --------------------------------------------------------------------------------------------------

def template_summary(f: dict) -> str:
    """Plain-English briefing from the facts alone (no Gemini)."""
    if f["risk_score"] is None:
        return "No forecast scores for tomorrow yet; check conditions before mobilizing."
    scores = [f"Predictive {f['predictive_score']:.1f}"] if f["predictive_score"] is not None else []
    if f["real_time_peak"] is not None:
        scores.append(f"Real-time peak {f['real_time_peak']:.1f}")
    parts = [f"{f['level'].capitalize()} risk tomorrow ({' · '.join(scores)} out of 10)."]
    if f["nws_alerts"]:
        parts.append(f"In force: {', '.join(f['nws_alerts'])}.")
    if f["peak_heat_index_f"] is not None and f["peak_heat_index_f"] >= 90:
        when = f" around {f['peak_heat_time']}" if f["peak_heat_time"] else ""
        parts.append(f"Heat index peaks near {f['peak_heat_index_f']}°F{when}.")
    if f["storm_window"]:
        parts.append(f"Thunderstorms likely {f['storm_window']}.")
    if f["max_gust_mph"] is not None and f["max_gust_mph"] >= 20:
        parts.append(f"Gusts to {f['max_gust_mph']} mph.")
    if f["rain_in"] is not None and f["rain_in"] >= 0.5:
        parts.append(f"{f['rain_in']:.1f} in of rain.")
    if f["snowfall_in"] is not None and f["snowfall_in"] >= 1:
        parts.append(f"{f['snowfall_in']:.0f} in of snow.")
    if f["ice_in"] is not None and f["ice_in"] >= 0.05:
        parts.append(f"{f['ice_in']:.2f} in of ice.")
    if f["min_wind_chill_f"] is not None and f["min_wind_chill_f"] <= 20:
        parts.append(f"Wind chill down to {f['min_wind_chill_f']}°F.")
    if f.get("peak_smoke_aqi") is not None:
        when = f" around {f['peak_smoke_time']}" if f.get("peak_smoke_time") else ""
        parts.append(f"Smoke: air quality index up to {f['peak_smoke_aqi']}{when}.")
    if f["recommendations"]:
        parts.append(f"{f['recommendations'][0]}.")
    elif f["level"] == "low":
        parts.append("Normal operations.")
    return " ".join(parts)


PROMPT = """You write next-day safety briefings for utility field-crew supervisors at power plant sites.
For each site below, write a briefing of at most 60 words in plain English: the overall risk, the hazards that
matter tomorrow and when, and the most important precaution. Use ONLY the facts given; don't add numbers, times,
hazards or advice that aren't in them. Null means unknown: leave it out, and never say that something is missing or
not provided. On a low-risk day say it's a normal work day and name the one hazard worth watching, if any.
Write temperatures in °F, wind in mph and rain in inches, as in the facts.

Return JSON: a list of {"site_id": <int>, "summary": "<briefing>"}, one per site.

Sites:
"""


def _numbers(text: str) -> set[float]:
    return {float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text)}


def valid_summary(summary: object, facts: dict) -> bool:
    """A Gemini summary is kept only if it's a sensible length and every number in it (over 12, so not clock
    hours) appears in the facts."""
    if not isinstance(summary, str) or not 20 <= len(summary) <= MAX_SUMMARY_CHARS:
        return False
    known = _numbers(json.dumps(facts))
    known |= {round(n) for n in known} | {round(n, 1) for n in known}
    return all(abs(n) <= 12 or n in known for n in _numbers(summary))


def gemini_models() -> list[str]:
    """settings.gemini_model, then the fallbacks, without repeats."""
    names = [settings.gemini_model, *settings.gemini_fallback_models.split(",")]
    return list(dict.fromkeys(n.strip() for n in names if n.strip()))


def gemini_summaries(batch: list[dict], client=None) -> tuple[dict[int, str], str | None]:
    """({site_id: summary}, the model that wrote them) from one Gemini request for a batch of {"site_id", "site",
    "facts"}. A busy model (RETRY_ON) is retried once; a retired (404) or still-failing one hands over to the next in
    gemini_models(). ({}, None) when none answers: the template covers those sites."""
    if client is None:
        if not settings.gemini_api_key:
            return {}, None
        from google import genai  # only when a key is set

        client = genai.Client(api_key=settings.gemini_api_key)
    from google.genai import types

    for model in gemini_models():
        for attempt in range(2):
            try:
                resp = client.models.generate_content(
                    model=model, contents=PROMPT + json.dumps(batch, default=str),
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2))
                items = json.loads(resp.text)
            except Exception as exc:  # network, quota, retired model, or a reply that isn't JSON
                log.warning("Gemini %s briefing batch failed: %s", model, str(exc)[:300])
                if getattr(exc, "code", None) in RETRY_ON and attempt == 0:
                    sleep(RETRY_WAIT_S)
                    continue
                break  # next model
            return _valid_summaries(items, batch), model
    return {}, None


def _valid_summaries(items: object, batch: list[dict]) -> dict[int, str]:
    facts = {b["site_id"]: b["facts"] for b in batch}
    out = {}
    for item in items if isinstance(items, list) else []:
        sid = item.get("site_id") if isinstance(item, dict) else None
        if sid in facts and valid_summary(item.get("summary"), facts[sid]):
            out[sid] = item["summary"].strip()
    return out


# --- Running ------------------------------------------------------------------------------------------------

UPSERT_SQL = """
INSERT INTO briefings (site_id, for_date, summary, details, generated_by, generated_at)
VALUES (%(site_id)s, %(for_date)s, %(summary)s, %(details)s, %(generated_by)s, now())
ON CONFLICT (site_id, for_date) DO UPDATE SET
    summary = EXCLUDED.summary, details = EXCLUDED.details, generated_by = EXCLUDED.generated_by,
    generated_at = now()
"""

SITES_SQL = "SELECT id, name, state, timezone FROM sites ORDER BY id"


def _load(conn, site_ids: list[int], first: datetime, last: datetime) -> dict[str, list[dict]]:
    window = {"ids": site_ids, "first": first, "last": last}
    return {
        "scores": conn.execute(
            "SELECT site_id, ts, scorer, score, factors FROM hazard_scores WHERE site_id = ANY(%(ids)s) "
            "AND ts >= %(first)s AND ts < %(last)s", window).fetchall(),
        "nws": conn.execute(
            "SELECT site_id, ts, temp_f, humidity_pct, wind_mph, gust_mph, precip_in, snowfall_in, ice_in, "
            "wind_chill_f, thunder_prob_pct, weather_code FROM nws_weather WHERE site_id = ANY(%(ids)s) "
            "AND is_forecast AND ts >= %(first)s AND ts < %(last)s", window).fetchall(),
        "open_meteo": conn.execute(
            "SELECT site_id, ts, temp_f, humidity_pct, wind_mph, gust_mph, precip_in, snowfall_in, weather_code "
            "FROM weather WHERE site_id = ANY(%(ids)s) AND is_forecast AND ts >= %(first)s AND ts < %(last)s",
            window).fetchall(),
        "air": conn.execute(
            "SELECT site_id, ts, us_aqi_pm2_5 FROM air_quality WHERE site_id = ANY(%(ids)s) AND is_forecast "
            "AND ts >= %(first)s AND ts < %(last)s", window).fetchall(),
        "alerts": conn.execute(
            "SELECT site_id, type, title, meta FROM alerts WHERE status = 'active' AND site_id = ANY(%(ids)s) "
            "AND (meta->>'ends' IS NULL OR (meta->>'ends')::timestamptz > %(first)s)", window).fetchall(),
    }


def _site_label(site: dict) -> str:
    return f"{site['name']}, {site['state']}" if site.get("state") else site["name"]


def build(sites: list[dict], now: datetime) -> list[dict]:
    """Briefing rows (not yet written) for these sites' next work day."""
    if not sites:
        return []
    days = {s["id"]: next_work_day(now, s["timezone"]) for s in sites}
    windows = {s["id"]: work_window(days[s["id"]], s["timezone"]) for s in sites}
    with connection() as conn:
        data = _load(conn, list(days), min(w[0] for w in windows.values()), max(w[1] for w in windows.values()))

    def rows_for(kind: str, sid: int) -> list[dict]:
        start, end = windows[sid]
        return [r for r in data[kind] if r["site_id"] == sid and ("ts" not in r or start <= r["ts"] < end)]

    entries = []
    for s in sites:
        sid = s["id"]
        facts = build_facts(rows_for("scores", sid), rows_for("nws", sid), rows_for("open_meteo", sid),
                            rows_for("alerts", sid), s["timezone"], rows_for("air", sid))
        entries.append({"site_id": sid, "site": _site_label(s), "facts": facts, "for_date": days[sid]})

    written: dict[int, tuple[str, str]] = {}  # site_id -> (summary, model)
    for i in range(0, len(entries), BATCH):
        batch = [{k: e[k] for k in ("site_id", "site", "facts")} for e in entries[i:i + BATCH]]
        summaries, model = gemini_summaries(batch)
        written |= {sid: (text, model) for sid, text in summaries.items()}
    if settings.gemini_api_key and entries and not written:
        log.error("Gemini wrote none of %d briefings (tried %s); every one is the template. See the warnings above.",
                  len(entries), ", ".join(gemini_models()))
    return [{"site_id": e["site_id"], "for_date": e["for_date"], "details": Jsonb(e["facts"]),
             "summary": written[e["site_id"]][0] if e["site_id"] in written else template_summary(e["facts"]),
             "generated_by": written[e["site_id"]][1] if e["site_id"] in written else "template"} for e in entries]


def _write(rows: list[dict]) -> int:
    if rows:
        with connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.executemany(UPSERT_SQL, rows)
    return len(rows)


def run_due(now: datetime | None = None) -> int:
    """Every 5 min: tomorrow's briefing for each site that's past 6 PM local and doesn't have one yet."""
    now = now or datetime.now(UTC)
    with connection() as conn:
        sites = conn.execute(SITES_SQL).fetchall()
        have = {(r["site_id"], r["for_date"]) for r in conn.execute(
            "SELECT site_id, for_date FROM briefings WHERE for_date >= %s", (now.date(),)).fetchall()}
    due = [s for s in sites if is_due(now, s["timezone"]) and (s["id"], next_work_day(now, s["timezone"])) not in have]
    n = _write(build(due, now))
    if n:
        log.info("briefings: wrote %d for tomorrow", n)
    return n


def generate_all(now: datetime | None = None, site_ids: list[int] | None = None) -> int:
    """Tomorrow's briefing now (the "Generate now" button): every site, or only `site_ids` (a manager's sites).
    Returns the count."""
    now = now or datetime.now(UTC)
    with connection() as conn:
        sites = conn.execute(SITES_SQL).fetchall()
    if site_ids is not None:
        wanted = set(site_ids)
        sites = [s for s in sites if s["id"] in wanted]
    n = _write(build(sites, now))
    log.info("briefings: generated %d on request%s", n, "" if site_ids is None else f" for {len(site_ids)} sites")
    return n


# params: {} for every site, or {"site_ids": [...]} (the API sends a manager's own sites).
jobs.HANDLERS["generate_briefings"] = lambda params: generate_all(site_ids=params.get("site_ids"))
