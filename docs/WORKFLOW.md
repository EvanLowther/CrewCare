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
- [ ] Load EIA-860M sites (`scripts/load_sites.py`)
- [ ] Start Storm Events + Open-Meteo history downloads
- [ ] Open-Meteo + NWS polling worker
- [ ] `rules-v1` scoring job
- [ ] Lightning rule + countdown + replay
- [ ] Training set + XGBoost
- [ ] USGS flood rule
- [ ] Score explanations
- [ ] Crew reports raise the score
- [ ] 6 PM briefing job (Gemini + template fallback)

### Person B (app)
- [ ] Real `/api/sites` + `/api/sites/{id}` queries
- [ ] Real `/api/alerts`, `/api/reports`, `/api/briefings` queries
- [x] Dashboard: Leaflet map + ranked list from mock data
- [ ] `scripts/seed_demo.py` (fake weather, scores, alerts in Tiger)
- [ ] Dashboard on the real API
- [ ] Site detail page
- [ ] Alert banner + live countdown
- [ ] Crew report form (photo + GPS pin)
- [ ] Deploy to an HTTPS URL; test the report form on a phone
- [ ] Briefings page + "Generate now"
