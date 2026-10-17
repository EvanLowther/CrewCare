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
| 4-8 | Open-Meteo + NWS polling worker | Dashboard: risk-coloured pins + ranked list, switch to real API |
| 8-12 | Training set, XGBoost, scoring job (rules-v1 fallback first) | Site detail page |
| 12-15 | Lightning rule + countdown + replay; USGS flood rule | Crew report form (photo + GPS pin) |
| 15-17 | Rest in shifts | |
| 17-19 | Score explanations; crew reports raise the score | Alert banner + live countdown |
| 19-21 | 6 PM briefing job with Gemini + template fallback | Briefings page + "Generate now" |
| 21-22 | Feature freeze, full demo run, bug fixes | |
| 22-24 | Seed demo data, record backup video, README + pitch, rehearse | |

If ML is behind at hour 12, ship `rules-v1` and swap the model in later. Cut order if behind: score explanations →
reports changing the score → Gemini briefing (use the template) → USGS (use NWS flood alerts only).
