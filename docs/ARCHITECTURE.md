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
- **API** reads all of those and writes only `hazard_reports` and `photos` (crew uploads).
- **Frontend** talks only to the API, always through its own origin: the browser calls `/api/...` on port 3000
  and `frontend/next.config.ts` forwards it to FastAPI on port 8000. So the site works at `localhost`, `127.0.0.1`
  or the computer's Wi-Fi address (phones) with no CORS setup. Alerts update by polling `GET /api/alerts?since=` every 10 s.

## Database (db/migrations/001_init.sql)

| Table | Kind | Written by | Purpose |
|---|---|---|---|
| `sites` | table | `scripts/load_sites.py` | ~60 Florida plants from EIA-860M. `geom` for distance queries, `timezone` for the 6 PM briefing (panhandle is Central). |
| `weather` | hypertable | worker | Hourly observed + forecast per site. `is_forecast` separates them. |
| `weather_daily` | continuous aggregate | Timescale | Daily max heat, total rain, soil moisture: ML features and "last 24 h". |
| `river_gauges`, `river_levels` | table, hypertable | worker | USGS stage/flow for flood rules. |
| `lightning_strikes` | hypertable | worker / replay | Every strike. `source` says replay, simulator or live. |
| `nws_alerts` | table | worker | Raw NWS alerts matched to sites. |
| `alerts` | table | worker | **What users see.** One active row per (site, type, dedupe_key). Lightning uses `all_clear_at`. |
| `hazard_scores` | hypertable | worker (ml/score.py) | 0-10 score, level, top factors, `kind` current/forecast. |
| `hazard_reports`, `photos` | table | API | Crew reports. Photos stored as resized JPEG bytes. |
| `briefings` | table | worker | One per site per day, generated 6 PM site-local. |
| `storm_events` | table | Person A loader | NOAA Storm Events, labels for ML training. |

Changing the schema: add `db/migrations/002_<name>.sql`. Never edit a migration that has been applied.

## Risk levels

`low` < 2.5 ≤ `moderate` < 5 ≤ `high` < 7.5 ≤ `extreme`. Defined in `backend/planit/ml/score.py` and
`frontend/src/lib/risk.ts`; keep them the same.

## Mock mode

`PLANIT_MOCK=1` makes every endpoint return data from `backend/planit/api/mock.py` (12 Florida sites, a live
lightning alert with countdown, a heat advisory, a flood warning, two crew reports). Person B builds against it
while Person A fills the database. Each endpoint's database version replaces the `not_built(...)` placeholder.
