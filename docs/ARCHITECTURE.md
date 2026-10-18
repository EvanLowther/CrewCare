# Architecture

```
 Open-Meteo   NWS weather + alerts   NWS river gauges   GOES lightning     Crew phones
 (+ air quality)  NIFC fires  USGS quakes                                  │
     │            │             │                 │                        │
     └────────────┴──────┬──────┴─────────────────┘                        │
                         ▼                                                 │
              ┌─────────────────────┐                                      │
              │  worker (Person A)  │  polls sources, runs rules,          │
              │  planit/worker, ml  │  scores sites, writes briefings      │
              └──────────┬──────────┘                                      │
                         ▼                                                 ▼
              ┌───────────────────────────────┐        ┌──────────────────────────┐
              │  Tiger Data (Postgres)        │◀──────▶│  API (FastAPI)           │
              │  TimescaleDB + PostGIS        │        │  planit/api              │
              └───────────────────────────────┘        └────────────┬─────────────┘
                                                                    │ JSON (models.py)
                                                                    ▼
                                                       ┌──────────────────────────┐
                                                       │  Next.js (Person B)      │
                                                       │  dashboard, site, report │
                                                       └──────────────────────────┘
```

**The one rule:** the worker and the API never call each other. They only share the database.
That lets each person build and test their half alone.

- **Worker** writes `weather`, `nws_weather`, `air_quality`, `river_levels`, `lightning_strikes`, `nws_alerts`,
  `alerts`, `hazard_scores`, `briefings`.
- **Fire, smoke and quake sources** (migration 007): Open-Meteo's air-quality API every 2 h (PM2.5 AQI, ~1,900 more
  calls a day), NIFC's current wildfires every 15 min and the USGS earthquake feed every 2 min, one national request
  each. Fires and quakes become `alerts` rows scored when they're raised (`meta.rule_severity`, `meta.action`).
- **Weather sources:** the NWS API (free, no daily cap) every 30 min for the Real-time score's weather, and one
  national alerts request every 2 min. Open-Meteo every 3 h for soil moisture, CAPE, hourly rain and the ML
  model's inputs (the model is trained on Open-Meteo's archive, so it keeps seeing the same source), ~1,800 of its
  10,000 free calls a day.
- **API** reads all of those and writes `hazard_reports` and `photos` (crew uploads), `users`, `site_members` and
  the sites managers create (docs/AUTH.md), `notifications` read marks and `push_subscriptions`, plus `job_requests` for the demo buttons: the worker's `jobs` poller
  picks those up within ~2 s (migration 002). Every read is filtered to the sites the viewer may see.
- **Frontend** talks only to the API, always through its own origin: the browser calls `/api/...` on port 3000
  and `frontend/next.config.ts` forwards it to FastAPI on port 8000. So the site works at `localhost`, `127.0.0.1`
  or the computer's Wi-Fi address (phones) with no CORS setup. Alerts update by polling `GET /api/alerts?since=` every 10 s.

## Database (db/migrations/001_init.sql)

| Table | Kind | Written by | Purpose |
|---|---|---|---|
| `sites` | table | `scripts/load_sites.py` | 160 power plants from EIA-860M: 60 hand-picked in Florida plus 100 across every other state (one each, the rest by share of large plants). `geom` for distance queries, `timezone` for the 6 PM briefing. |
| `weather` | hypertable | worker | Hourly observed + forecast per site. `is_forecast` separates them. Snowfall and snow depth since 004. |
| `weather_daily` | continuous aggregate | Timescale | Daily max heat, total rain, soil moisture: ML features and "last 24 h". |
| `nws_weather` | hypertable | worker (`ingest/nws_weather.py`) | NWS station observation + 72 h gridpoint forecast per site: wind chill, WBGT, visibility, ice, thunder chance. Real-time score only. 005; `sites.nws_*` hold each site's grid, station and alert zones. |
| `air_quality` | hypertable | worker (`ingest/air_quality.py`) | Hourly US AQI, PM2.5 AQI and PM2.5 per site, observed + 2-day forecast (Open-Meteo / CAMS). Smoke in the Real-time score and the Predictive smoke floor. 007. |
| `river_gauges`, `river_levels` | table, hypertable | worker (`ingest/river.py`) | NOAA NWPS river gauges within 2 mi of a site (`sites.usgs_gauge_id` = the NWPS id) with NWS flood stages; stage, 48 h forecast peak and flood category every 15 min. `rules/flood.py` turns them (and 12 h of rain) into `flood` alerts, `meta.source = 'river'`. 012. |
| `lightning_strikes` | hypertable | worker (`ingest/glm.py`) / replay | Flashes within 10 mi of a site: `glm` (GOES-East and GOES-West, live, every 20 s) or `replay` (the demo button). `rules/lightning.py` turns them into stop-work alerts. |
| `nws_alerts` | table | worker | Raw NWS alerts matched to sites. |
| `alerts` | table | worker | **What users see.** One active row per (site, type, dedupe_key). Lightning uses `all_clear_at`. `meta.source` says who raised it: `nws`, `nifc` (wildfire), `usgs` (earthquake, `meta.ends` 12 h after the quake), `river` (flood risk, 012), `crew` (a medium or high crew report, `meta.report_id`; scored from the report itself, not the alert). Types `air_quality` and `earthquake` since 007. |
| `hazard_scores` | hypertable | worker (ml/score.py) | 0-10 score, level, top factors, `kind` current/forecast. |
| `hazard_reports`, `photos` | table | API | Crew reports. Photos stored as resized JPEG bytes. Active reports on a site or within 1 mi of it count in both scores (`hazards.crew_report`: by type and severity, confirmed by live data or a manager, `confirmed_by` / `confirmed_at` since 013). |
| `briefings` | table | worker | One per site per day, generated 6 PM site-local. |
| `storm_events` | table | Person A loader | NOAA Storm Events, labels for ML training: Florida 2023-2025, every state 2024-2025. |
| `job_requests` | table | API (demo buttons, new sites) | Requests the worker runs: `lightning_replay`, `generate_briefings`, and `site_setup` (008: a site that was just created or moved gets its weather and scores at once). 002. |
| `users`, `site_members` | table | API | Who signed in, their role, and which sites they're on. 006, see AUTH.md. |
| `score_snapshots` | hypertable | trigger | Every 5-minute current score (both scorers), copied by a trigger on `hazard_scores`, which keeps only the hour's latest; the site page charts the last 12 h. Kept 14 days. 013. |
| `notifications`, `push_subscriptions` | table | triggers, API | Crew reports, danger alerts and briefings for each site member, written by triggers on `hazard_reports`, `alerts` and `briefings`; streamed to open pages and pushed to devices by the API (`api/push.py`). 011. |

Changing the schema: add `db/migrations/002_<name>.sql`. Never edit a migration that has been applied.

## Risk levels

Two scorers write `hazard_scores` side by side (`scorer` column, migration 003), and the dashboard's switch picks one
(`?model=rules|ml`, default `ml`):

- **Real-time** (`scorer='rules'`, rules-v2): measured conditions against work rules, described below.
- **Predictive** (`scorer='ml'`, e.g. `xgb-2026-10-17-us`): one national XGBoost model's hazard-day likelihood
  (storms, floods, heat, wind, cold, winter weather, wildfire and dust; latitude and longitude tell it what's
  normal where), on the **same 0-10 scale** as Real-time: a probability scores as the Real-time score with the same
  historical hazard-day odds (`scale` in the model's `.meta.json`, `ml/scale.py`); below 1.0, where every calm day
  is Real-time 0, the odds are spread on a log scale instead. On top, per hour: alert points, a floor at the
  Real-time severity of any NWS warning, lightning, wildfire or earthquake alert in force, of smoke and of fire
  weather, and the OSHA heat floor (`backend/planit/ml/score.py`, `ml/model.py`).

| Score | Level | Meaning for the crew |
|---|---|---|
| 0 – 2.4 | low | Normal operations |
| 2.5 – 4.9 | moderate | Work with precautions |
| 5 – 7.4 | high | Restricted work |
| 7.5 – 10 | extreme | Stop non-essential work |

Bands are defined in `backend/planit/ml/score.py` (`level_for`) and `frontend/src/lib/risk.ts`; keep them the same.

rules-v2 scores every hazard on that one 0-10 scale in `backend/planit/hazards.py`, anchored to published work rules:
the NWS heat index on OSHA's bands (91°F moderate, 103°F high, 115°F "no strenuous work" ≈ 9), lightning = 10,
forecast thunderstorms 8-9, wind gusts against lift limits (20 mph personnel lifts, 28 mph aerial lifts, 40 mph
elevated work), rain rate, 24 h rain, saturated ground, and NWS alerts by event (Tornado Warning 10, Wind
Advisory 4.5, ...). The site score is the worst kind of hazard plus 0.25 × the second and 0.10 × the third, each only
if it's high (≥ 5) on its own; hazards of the same kind (a Wind Advisory and the gusts it warns about) count once.
Each factor carries a recommended `action` for supervisors.

The API's `heat_index_f` is the NWS heat index computed from temperature and humidity. The stored
`weather.heat_index_f` column is Open-Meteo's "feels like" value, which the model's features are trained on.

## Mock mode

`PLANIT_MOCK=1` makes every endpoint return data from `backend/planit/api/mock.py` (12 Florida sites, a live
lightning alert with countdown, a heat advisory, a flood warning, two crew reports). Person B builds against it
while Person A fills the database. Each endpoint's database version replaces the `not_built(...)` placeholder.
