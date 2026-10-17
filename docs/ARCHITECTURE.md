# Architecture

```
 Open-Meteo   NWS alerts   USGS gauges   Lightning replay / feed      Crew phones
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

- **Worker** writes `weather`, `river_levels`, `lightning_strikes`, `nws_alerts`, `alerts`, `hazard_scores`, `briefings`.
- **API** reads all of those and writes only `hazard_reports` and `photos` (crew uploads), plus `job_requests`
  for the demo buttons: the worker's `jobs` poller picks those up within ~2 s (migration 002).
- **Frontend** talks only to the API, always through its own origin: the browser calls `/api/...` on port 3000
  and `frontend/next.config.ts` forwards it to FastAPI on port 8000. So the site works at `localhost`, `127.0.0.1`
  or the computer's Wi-Fi address (phones) with no CORS setup. Alerts update by polling `GET /api/alerts?since=` every 10 s.

## Database (db/migrations/001_init.sql)

| Table | Kind | Written by | Purpose |
|---|---|---|---|
| `sites` | table | `scripts/load_sites.py` | 160 power plants from EIA-860M: 60 hand-picked in Florida plus 100 across every other state (one each, the rest by share of large plants). `geom` for distance queries, `timezone` for the 6 PM briefing. |
| `weather` | hypertable | worker | Hourly observed + forecast per site. `is_forecast` separates them. Snowfall and snow depth since 004. |
| `weather_daily` | continuous aggregate | Timescale | Daily max heat, total rain, soil moisture: ML features and "last 24 h". |
| `river_gauges`, `river_levels` | table, hypertable | worker | USGS stage/flow for flood rules. |
| `lightning_strikes` | hypertable | worker / replay | Every strike. `source` says replay, simulator or live. |
| `nws_alerts` | table | worker | Raw NWS alerts matched to sites. |
| `alerts` | table | worker | **What users see.** One active row per (site, type, dedupe_key). Lightning uses `all_clear_at`. |
| `hazard_scores` | hypertable | worker (ml/score.py) | 0-10 score, level, top factors, `kind` current/forecast. |
| `hazard_reports`, `photos` | table | API | Crew reports. Photos stored as resized JPEG bytes. |
| `briefings` | table | worker | One per site per day, generated 6 PM site-local. |
| `storm_events` | table | Person A loader | NOAA Storm Events, labels for ML training: Florida 2023-2025, every state 2024-2025. |
| `job_requests` | table | API (demo buttons) | Requests the worker runs: `lightning_replay`, `generate_briefings`. 002. |

Changing the schema: add `db/migrations/002_<name>.sql`. Never edit a migration that has been applied.

## Risk levels

Two scorers write `hazard_scores` side by side (`scorer` column, migration 003), and the dashboard's switch picks one
(`?model=rules|ml`, default `ml`):

- **Real-time** (`scorer='rules'`, rules-v2): measured conditions against work rules, described below.
- **Predictive** (`scorer='ml'`, e.g. `xgb-2026-10-17-us`): one national XGBoost model's hazard-day likelihood
  (storms, floods, heat, wind, cold, winter weather, wildfire and dust; latitude and longitude tell it what's
  normal where), plus the OSHA heat floor, alert points and the lightning floor (`backend/planit/ml/score.py`,
  `ml/model.py`).

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
