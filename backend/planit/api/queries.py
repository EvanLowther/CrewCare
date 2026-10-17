"""Owner: Person B. Database reads behind the API endpoints.

Each function returns models from planit/models.py, so the JSON matches mock mode exactly.
Time-series reads are bounded to recent days so they stay fast as `weather` grows with history.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from planit.config import settings
from planit.db import connection
from planit.models import (
    Alert,
    Conditions,
    HazardReport,
    Last24h,
    Risk,
    RiskFactor,
    RiskPoint,
    SiteDetail,
    SiteSummary,
)

REPORT_RADIUS_M = 8046.7  # 5 miles: crew reports shown on a site's page

_SEVERITY_RANK = "CASE severity WHEN 'danger' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END"

# One row per site: latest current score, active alert count and most severe alert, latest heat index.
_SITE_SUMMARY_SQL = f"""
WITH latest_score AS (
    SELECT DISTINCT ON (site_id) site_id, score, level, factors, model_version, computed_at
    FROM hazard_scores
    WHERE kind = 'current' AND scorer = %(scorer)s
      AND ts > now() - interval '2 days' AND ts <= now() + interval '1 hour'
    ORDER BY site_id, ts DESC
),
active_alerts AS (
    SELECT site_id, count(*) AS n,
           (array_agg(type ORDER BY {_SEVERITY_RANK}, started_at DESC))[1] AS top_type
    FROM alerts
    WHERE status = 'active'
    GROUP BY site_id
),
latest_heat AS (
    SELECT DISTINCT ON (site_id) site_id, heat_index_f
    FROM weather
    WHERE NOT is_forecast AND ts > now() - interval '2 days' AND ts <= now()
    ORDER BY site_id, ts DESC
)
SELECT s.id, s.name, s.utility, s.county, s.plant_type, s.capacity_mw, s.latitude, s.longitude, s.timezone,
       ls.score, ls.level, ls.factors, ls.model_version, ls.computed_at,
       coalesce(aa.n, 0) AS active_alert_count, aa.top_type, lh.heat_index_f
FROM sites s
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


def _summary(row: dict) -> SiteSummary:
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
        heat_index_f=_float(row["heat_index_f"]),
    )


def _conditions(row: dict) -> Conditions:
    return Conditions(**{k: (row[k] if k in ("ts", "weather_code") else _float(row[k])) for k in row})


def default_scorer() -> str:
    """Which hazard_scores to show when the client doesn't ask: the ML model unless PLANIT_SCORE_MODEL=rules."""
    return "ml" if settings.score_model == "xgb" else "rules"


def list_sites(scorer: str | None = None) -> list[SiteSummary]:
    """Highest risk first by `scorer` ('ml' or 'rules'); unscored sites last, largest plants first among them."""
    with connection() as conn:
        rows = conn.execute(
            _SITE_SUMMARY_SQL + " ORDER BY ls.score DESC NULLS LAST, s.capacity_mw DESC NULLS LAST, s.id",
            {"scorer": scorer or default_scorer()},
        ).fetchall()
    return [_summary(r) for r in rows]


def list_alerts(site_id: int | None = None, since: datetime | None = None,
                include_cleared: bool = False) -> list[Alert]:
    """Active alerts, or with `since` every alert updated after it (so the client also sees ones that cleared)."""
    where, params = [], []
    if site_id is not None:
        where.append("a.site_id = %s")
        params.append(site_id)
    if since is not None:
        where.append("a.updated_at > %s")
        params.append(since)
    elif not include_cleared:
        where.append("a.status = 'active'")
    sql = _ALERT_SQL + (" WHERE " + " AND ".join(where) if where else "")
    sql += f" ORDER BY {_SEVERITY_RANK.replace('severity', 'a.severity')}, a.started_at DESC"
    with connection() as conn:
        return [Alert(**r) for r in conn.execute(sql, params).fetchall()]


def get_site(site_id: int, scorer: str | None = None) -> SiteDetail | None:
    scorer = scorer or default_scorer()
    with connection() as conn:
        row = conn.execute(_SITE_SUMMARY_SQL + " WHERE s.id = %(site_id)s",
                           {"scorer": scorer, "site_id": site_id}).fetchone()
        if row is None:
            return None

        current = conn.execute(
            f"SELECT {_CONDITION_COLS} FROM weather WHERE site_id = %s AND NOT is_forecast "
            "AND ts > now() - interval '2 days' AND ts <= now() ORDER BY ts DESC LIMIT 1",
            (site_id,),
        ).fetchone()

        last24 = conn.execute(
            "SELECT count(*) AS n, sum(precip_in) AS total_precip_in, max(heat_index_f) AS max_heat_index_f, "
            "max(gust_mph) AS max_gust_mph FROM weather "
            "WHERE site_id = %s AND NOT is_forecast AND ts > now() - interval '24 hours' AND ts <= now()",
            (site_id,),
        ).fetchone()

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

        reports = conn.execute(
            "SELECT r.id, r.site_id, r.latitude, r.longitude, r.hazard_type, r.severity, r.description, "
            "r.reporter_name, r.photo_id, r.status, r.created_at, r.expires_at "
            "FROM hazard_reports r JOIN sites s ON s.id = %s "
            "WHERE r.status = 'active' AND (r.expires_at IS NULL OR r.expires_at > now()) "
            "AND ST_DWithin(r.geom, s.geom, %s) ORDER BY r.created_at DESC",
            (site_id, REPORT_RADIUS_M),
        ).fetchall()

        history = conn.execute(
            "SELECT ts, score, level, kind FROM hazard_scores WHERE site_id = %s AND scorer = %s "
            "AND ts >= now() - interval '24 hours' AND ts <= now() + interval '24 hours' ORDER BY ts, kind",
            (site_id, scorer),
        ).fetchall()

    return SiteDetail(
        site=_summary(row),
        conditions=_conditions(current) if current else None,
        last_24h=Last24h(
            total_precip_in=_float(last24["total_precip_in"]),
            max_heat_index_f=_float(last24["max_heat_index_f"]),
            max_gust_mph=_float(last24["max_gust_mph"]),
        ) if last24["n"] else None,
        forecast=[_conditions(r) for r in forecast],
        alerts=[Alert(**r) for r in alerts],
        reports=[
            HazardReport(**{k: v for k, v in r.items() if k != "photo_id"},
                         photo_url=f"/api/photos/{r['photo_id']}" if r["photo_id"] else None)
            for r in reports
        ],
        risk_history=[RiskPoint(ts=r["ts"], score=float(r["score"]), level=r["level"], kind=r["kind"])
                      for r in history],
    )
