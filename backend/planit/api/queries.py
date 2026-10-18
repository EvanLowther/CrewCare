"""Owner: Person B. Database reads behind the API endpoints.

Each function returns models from planit/models.py, so the JSON matches mock mode exactly.
Time-series reads are bounded to recent days so they stay fast as `weather` grows with history.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from planit.api.access import can_delete, can_manage, can_view, signed_photo_url, visible_sites_sql
from planit.auth import CurrentUser
from planit.config import settings
from planit.db import connection
from planit.hazards import nws_heat_index
from planit.models import (
    AirQuality,
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

# A site's page lists crew reports filed on it plus any within 5 mi (that the viewer may see).
REPORT_RADIUS_M = 8046.7

_SEVERITY_RANK = "CASE severity WHEN 'danger' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END"

# One row per site: latest current score (or, with %(ahead)s > 0, the newest forecast for that many hours from now),
# active alert count and most severe alert, latest heat index.
_SITE_SUMMARY_SQL = f"""
WITH latest_score AS (
    SELECT DISTINCT ON (site_id) site_id, score, level, factors, model_version, computed_at
    FROM hazard_scores
    WHERE scorer = %(scorer)s AND (
        (%(ahead)s = 0 AND kind = 'current' AND ts > now() - interval '2 days' AND ts <= now() + interval '1 hour')
        OR (%(ahead)s > 0 AND ts = date_trunc('hour', now()) + %(ahead)s * interval '1 hour'))
    ORDER BY site_id, ts DESC, computed_at DESC
),
active_alerts AS (
    SELECT site_id, count(*) AS n,
           (array_agg(type ORDER BY {_SEVERITY_RANK}, started_at DESC))[1] AS top_type
    FROM alerts
    WHERE status = 'active'
    GROUP BY site_id
),
latest_heat AS (
    SELECT DISTINCT ON (site_id) site_id, temp_f, humidity_pct
    FROM weather
    WHERE NOT is_forecast AND ts > now() - interval '2 days' AND ts <= now()
    ORDER BY site_id, ts DESC
)
SELECT s.id, s.name, s.utility, s.county, s.plant_type, s.capacity_mw, s.latitude, s.longitude, s.timezone,
       s.is_reference, s.description, s.created_by, me.role AS my_role,
       ls.score, ls.level, ls.factors, ls.model_version, ls.computed_at,
       coalesce(aa.n, 0) AS active_alert_count, aa.top_type, lh.temp_f, lh.humidity_pct
FROM sites s
LEFT JOIN site_members me ON me.site_id = s.id AND me.user_id = %(me_id)s
LEFT JOIN latest_score ls ON ls.site_id = s.id
LEFT JOIN active_alerts aa ON aa.site_id = s.id
LEFT JOIN latest_heat lh ON lh.site_id = s.id
"""

_ALERT_SQL = """
SELECT a.id, a.site_id, s.name AS site_name, a.type, a.severity, a.title, a.message, a.status, a.started_at,
       a.all_clear_at, a.cleared_at, a.meta, a.updated_at
FROM alerts a JOIN sites s ON s.id = a.site_id
"""

_CONDITION_COLS = ("ts, temp_f, heat_index_f, humidity_pct, precip_in, precip_prob_pct, wind_mph, gust_mph, "
                   "cape_jkg, soil_moisture, weather_code")


def _float(v: Any) -> float | None:
    return None if v is None else float(v)


def _summary(row: dict, user: CurrentUser | None) -> SiteSummary:
    risk = None
    if row["score"] is not None:
        risk = Risk(
            score=float(row["score"]),
            level=row["level"],
            factors=[RiskFactor(**f) for f in (row["factors"] or [])],
            model_version=row["model_version"],
            updated_at=row["computed_at"],
        )
    return SiteSummary(
        id=row["id"], name=row["name"], utility=row["utility"], county=row["county"],
        plant_type=row["plant_type"], capacity_mw=_float(row["capacity_mw"]),
        latitude=row["latitude"], longitude=row["longitude"], timezone=row["timezone"],
        risk=risk, active_alert_count=row["active_alert_count"], top_alert=row["top_type"],
        heat_index_f=nws_heat_index(_float(row["temp_f"]), _float(row["humidity_pct"])),
        is_reference=row["is_reference"], description=row["description"], my_role=row["my_role"],
        can_manage=can_manage(user, row["my_role"]),
        can_delete=can_delete(user, row["my_role"], row["created_by"]),
    )


def _conditions(row: dict) -> Conditions:
    """A weather row for the API. heat_index_f is the NWS heat index (what the score uses and OSHA's bands are
    defined on), computed from temperature and humidity; the stored column is Open-Meteo's "feels like"."""
    values = {k: (row[k] if k in ("ts", "weather_code") else _float(row[k])) for k in row}
    values["heat_index_f"] = nws_heat_index(values["temp_f"], values["humidity_pct"])
    return Conditions(**values)


def _last_24h(rows: list[dict]) -> Last24h | None:
    if not rows:
        return None
    rain = [float(r["precip_in"]) for r in rows if r["precip_in"] is not None]
    heat = [h for r in rows if (h := nws_heat_index(_float(r["temp_f"]), _float(r["humidity_pct"]))) is not None]
    gust = [float(r["gust_mph"]) for r in rows if r["gust_mph"] is not None]
    return Last24h(total_precip_in=round(sum(rain), 2) if rain else None, max_heat_index_f=max(heat, default=None),
                   max_gust_mph=max(gust, default=None))


def default_scorer() -> str:
    """Which hazard_scores to show when the client doesn't ask: the ML model unless PLANIT_SCORE_MODEL=rules."""
    return "ml" if settings.score_model == "xgb" else "rules"


def list_sites(scorer: str | None = None, user: CurrentUser | None = None, hours_ahead: int = 0) -> list[SiteSummary]:
    """Sites `user` may see, highest risk first by `scorer` ('ml' or 'rules'); unscored sites last, largest plants
    first among them. `hours_ahead` (1-24) scores each site with its forecast for that hour instead of now."""
    visible, params = visible_sites_sql(user)
    with connection() as conn:
        rows = conn.execute(
            _SITE_SUMMARY_SQL + f" WHERE {visible} "
            "ORDER BY ls.score DESC NULLS LAST, s.capacity_mw DESC NULLS LAST, s.id",
            {"scorer": scorer or default_scorer(), "ahead": hours_ahead, "me_id": user.id if user else None,
             **params},
        ).fetchall()
    return [_summary(r, user) for r in rows]


def list_alerts(site_id: int | None = None, since: datetime | None = None, include_cleared: bool = False,
                user: CurrentUser | None = None) -> list[Alert]:
    """Active alerts on sites `user` may see, or with `since` every alert updated after it (so the client also sees
    ones that cleared)."""
    visible, params = visible_sites_sql(user)
    where = [visible]
    if site_id is not None:
        where.append("a.site_id = %(site_id)s")
        params["site_id"] = site_id
    if since is not None:
        where.append("a.updated_at > %(since)s")
        params["since"] = since
    elif not include_cleared:
        where.append("a.status = 'active'")
    sql = _ALERT_SQL + " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {_SEVERITY_RANK.replace('severity', 'a.severity')}, a.started_at DESC"
    with connection() as conn:
        return [Alert(**r) for r in conn.execute(sql, params).fetchall()]


def list_briefings(for_date: date, user: CurrentUser | None = None) -> list[Briefing]:
    """Briefings for one work day (written by the worker's 6 PM job) on sites `user` may see, riskiest first."""
    visible, params = visible_sites_sql(user)
    with connection() as conn:
        rows = conn.execute(
            "SELECT b.id, b.site_id, s.name AS site_name, b.for_date, b.summary, b.details, b.generated_by, "
            "b.generated_at FROM briefings b JOIN sites s ON s.id = b.site_id "
            f"WHERE b.for_date = %(for_date)s AND {visible} "
            "ORDER BY (b.details->>'risk_score')::float DESC NULLS LAST, s.name",
            {"for_date": for_date, **params},
        ).fetchall()
    return [Briefing(**r) for r in rows]


class SiteHidden(Exception):
    """The site exists but the viewer isn't allowed to see it."""


def get_site(site_id: int, scorer: str | None = None, user: CurrentUser | None = None) -> SiteDetail | None:
    """None if there's no such site; raises SiteHidden if `user` may not see it."""
    scorer = scorer or default_scorer()
    with connection() as conn:
        row = conn.execute(_SITE_SUMMARY_SQL + " WHERE s.id = %(site_id)s",
                           {"scorer": scorer, "ahead": 0, "site_id": site_id,
                            "me_id": user.id if user else None}).fetchone()
        if row is None:
            return None
        if not can_view(user, row["is_reference"], row["my_role"]):
            raise SiteHidden

        current = conn.execute(
            f"SELECT {_CONDITION_COLS} FROM weather WHERE site_id = %s AND NOT is_forecast "
            "AND ts > now() - interval '2 days' AND ts <= now() ORDER BY ts DESC LIMIT 1",
            (site_id,),
        ).fetchone()

        air = conn.execute(
            "SELECT ts, us_aqi, us_aqi_pm2_5, pm2_5_ugm3 FROM air_quality WHERE site_id = %s AND NOT is_forecast "
            "AND ts > now() - interval '6 hours' AND ts <= now() ORDER BY ts DESC LIMIT 1",
            (site_id,),
        ).fetchone()

        past_day = conn.execute(
            "SELECT precip_in, temp_f, humidity_pct, gust_mph FROM weather "
            "WHERE site_id = %s AND NOT is_forecast AND ts > now() - interval '24 hours' AND ts <= now()",
            (site_id,),
        ).fetchall()

        forecast = conn.execute(
            f"SELECT {_CONDITION_COLS} FROM weather WHERE site_id = %s AND is_forecast "
            "AND ts > now() AND ts <= now() + interval '48 hours' ORDER BY ts LIMIT 48",
            (site_id,),
        ).fetchall()

        alerts = conn.execute(
            _ALERT_SQL + " WHERE a.site_id = %s AND a.status = 'active' "
            f"ORDER BY {_SEVERITY_RANK.replace('severity', 'a.severity')}, a.started_at DESC",
            (site_id,),
        ).fetchall()

        # Reports filed on this site, plus nearby ones on sites the viewer may see (or legacy ones with no site).
        visible, vis_params = visible_sites_sql(user, alias="rs")
        reports = conn.execute(
            "SELECT r.id, r.site_id, r.latitude, r.longitude, r.hazard_type, r.severity, r.description, "
            "r.reporter_name, r.photo_id, r.status, r.created_at, r.expires_at "
            "FROM hazard_reports r JOIN sites s ON s.id = %(site_id)s LEFT JOIN sites rs ON rs.id = r.site_id "
            "WHERE r.status = 'active' AND (r.expires_at IS NULL OR r.expires_at > now()) "
            f"AND (r.site_id = s.id OR (ST_DWithin(r.geom, s.geom, %(radius)s) AND (rs.id IS NULL OR {visible}))) "
            "ORDER BY r.created_at DESC",
            {"site_id": site_id, "radius": REPORT_RADIUS_M, **vis_params},
        ).fetchall()

        history = conn.execute(
            "SELECT ts, score, level, kind FROM hazard_scores WHERE site_id = %s AND scorer = %s "
            "AND ts >= now() - interval '24 hours' AND ts <= now() + interval '24 hours' ORDER BY ts, kind",
            (site_id, scorer),
        ).fetchall()

    return SiteDetail(
        site=_summary(row, user),
        conditions=_conditions(current) if current else None,
        last_24h=_last_24h(past_day),
        air_quality=AirQuality(**{k: v if k == "ts" else _float(v) for k, v in air.items()}) if air else None,
        forecast=[_conditions(r) for r in forecast],
        alerts=[Alert(**r) for r in alerts],
        reports=[
            HazardReport(**{k: v for k, v in r.items() if k != "photo_id"},
                         photo_url=signed_photo_url(r["photo_id"]) if r["photo_id"] else None)
            for r in reports
        ],
        risk_history=[RiskPoint(ts=r["ts"], score=float(r["score"]), level=r["level"], kind=r["kind"])
                      for r in history],
    )
