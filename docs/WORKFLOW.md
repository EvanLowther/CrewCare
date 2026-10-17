# Workflow

## Branches and PRs
- `main` always runs. Never push broken code to it.
- One branch per plan step: `a/open-meteo-ingest`, `b/dashboard-map`.
- Open a PR, let CI pass, merge yourself (no review wait at a hackathon), then pull `main` often.

## Who touches what
| Area | Person A | Person B |
|---|---|---|
| `backend/planit/worker/`, `backend/planit/ml/`, `backend/scripts/` | ✅ | |
| `backend/planit/api/`, `frontend/` | | ✅ |
| `backend/planit/models.py`, `db/migrations/` | heads-up first | heads-up first |

## Plan (24 h)
| Hours | Person A (data + ML) | Person B (app) |
|---|---|---|
| 0-1 | ✅ Together: schema, API contract, repo, Tiger instance | |
| 1-4 | Load EIA-860M sites; start Storm Events + Open-Meteo history downloads | Real `/api/sites` + `/api/sites/{id}` queries; Leaflet map from mock data |
| 4-8 | Open-Meteo + NWS polling worker; `rules-v1` scoring job | `scripts/seed_demo.py` (fake weather, scores, alerts in Tiger; heads-up to A); dashboard: risk-coloured pins + ranked list, switch to real API |
| 4-8 | ✅ Together (30 min): `job_requests` table so the demo buttons reach the worker through the database | |
| 8-12 | Lightning rule + countdown + replay | Site detail page; alert banner + live countdown |
| 12 | ✅ Together: full app run with `PLANIT_MOCK=0` | |
| 12-15 | Training set, XGBoost; USGS flood rule | Crew report form (photo + GPS pin) |
| 15-17 | Rest in shifts | |
| 17-19 | Score explanations; crew reports raise the score | Deploy to an HTTPS URL (phone camera and GPS need it); test the report form on a phone |
| 18 | ✅ Together: full app run with `PLANIT_MOCK=0` on the deployed URL | |
| 19-21 | 6 PM briefing job with Gemini + template fallback | Briefings page + "Generate now" |
| 21-22 | Feature freeze, full demo run, bug fixes | |
| 22-24 | Refresh demo data, record backup video, README + pitch, rehearse | |

If ML is behind at hour 15, ship `rules-v1` and swap the model in later. Cut order if behind: USGS (use NWS flood
alerts only) → reports changing the score → Gemini briefing (use the template) → score explanations. Keep
explanations longest: they are what the AI track judges look for.

## Checklist
Tick items in the PR that finishes them.

### Together
- [x] Schema, API contract, repo, Tiger instance (`001_init.sql` applied)
- [ ] `job_requests` table for the demo buttons (migration 002, API inserts, worker polls)
- [ ] Hour 12 check: full app with `PLANIT_MOCK=0`
- [ ] Hour 18 check: full app with `PLANIT_MOCK=0` on the deployed URL
- [ ] Feature freeze, full demo run, bug fixes
- [ ] Refresh demo data, record backup video, README + pitch, rehearse

### Person A (data + ML)
- [x] Load EIA-860M sites (`scripts/load_sites.py`)
- [x] Start Storm Events + Open-Meteo history downloads
- [x] Open-Meteo + NWS polling worker
- [x] `rules-v1` scoring job
- [x] rules-v2: hazards on one 0-10 scale from OSHA/NWS work rules, with recommended actions
- [ ] Lightning rule + countdown + replay
- [x] Training set + XGBoost
- [ ] USGS flood rule
- [ ] Score explanations
- [ ] Crew reports raise the score
- [ ] 6 PM briefing job (Gemini + template fallback)

### Person B (app)
- [x] Real `/api/sites` + `/api/sites/{id}` queries
- [ ] Real `/api/alerts`, `/api/reports`, `/api/briefings` queries
- [x] Dashboard: Leaflet map + ranked list from mock data
- [ ] `scripts/seed_demo.py` (fake weather, scores, alerts in Tiger)
- [x] Dashboard on the real API
- [x] Site detail page
- [ ] Alert banner + live countdown
- [ ] Crew report form (photo + GPS pin)
- [ ] Deploy to an HTTPS URL; test the report form on a phone
- [ ] Briefings page + "Generate now"

## US expansion

Goal: power plant sites in every state, scored for every hazard a crew can meet anywhere in the US, not only
Florida's. 160 sites: the 60 Florida plants plus 100 more (one per state, the rest by each state's share of
plants ≥ 50 MW). Sized for Open-Meteo's free tier (10,000 calls/day). `a/us-sites` goes first.

### Together
- [ ] Migration `004_us_scope.sql`: `weather.snowfall_in`, `weather.snow_depth_ft`; drop `sites.state DEFAULT 'FL'`
- [ ] New alert types for national hazards (`winter`, `cold`, `air_quality`, `earthquake`, `landslide`):
      `AlertType` in models.py + alerts CHECK, heads-up first
- [ ] Full app run with `PLANIT_MOCK=0` on the national site list; refresh the demo data

### Person A (data + ML)
- [ ] `a/us-sites`: 100 more plants across all states, real state codes, timezones by lat/lon (Pacific, Mountain,
      Arizona without DST, Alaska, Hawaii); 2-year weather history; national Storm Events matched on
      (state, county); retrain with cold/winter/wildfire/fog/dust labels and location, cold and snow features;
      evaluate per region
- [ ] Open-Meteo budget: soil moisture in its own request every 3 h so the 30-min poll stays at ≤ 10 variables
      (160 sites × 48 polls ≈ 7,700 calls/day)
- [ ] NWS alerts polled by state or nationally instead of one request per site
- [ ] Lightning rule + countdown + replay (the existing item); then live strikes (GOES GLM)
- [ ] Flood replay demo button, like the lightning one
- [ ] River flood rule with NWS flood stages (replaces "USGS flood rule"); must cover the Mississippi
- [ ] rules-v2 for national hazards: wind chill / extreme cold, snow / ice / freezing rain, active wildfire,
      smoke / AQI, fog / dust visibility, debris flow, earthquake, coastal flood; actions for their NWS events;
      new hazard kinds so they compound correctly
- [ ] Score baseline per region, if "5" should mean "unusual for this site" rather than nationally
- [ ] Later: separate models per hazard (storm, winter, flood, heat) instead of one "hazard day" model
- [ ] 6 PM briefing job works for every US timezone

### Person B (app)
- [ ] `mock.py` sample sites across the country and timezones; contract tests still pass
- [ ] Map opens on the whole US and fits the sites; marker clustering; Alaska/Hawaii reachable
- [ ] `?state=` on `/api/sites` and `/api/alerts`; state and hazard filters on the ranked list
- [ ] Icons, colours and labels for the new alert types and factor kinds
- [ ] Crew report types for national hazards (ice, smoke, snakes/bears, sinkhole, ...)
- [ ] Replace the "Florida" copy in the dashboard, sidebar, README and pitch
