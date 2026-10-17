# PlanIT Control

Real-time hazard monitoring for utility field crews at ~60 Florida power plant sites (SwampHacks, Sperry Tech challenge).
Combines weather, heat, lightning, flooding, soil saturation and crew hazard reports into one 0-10 risk score per site,
fires stop-work alerts, and sends a 6 PM next-day safety briefing.

## Quick start

Needs Python 3.11+, Node 22 and pnpm.

```bash
make setup      # installs everything, creates .env from .env.example
make api        # terminal 1: http://localhost:8000/docs
make web        # terminal 2: http://localhost:3000
```

`.env` starts with `PLANIT_MOCK=1`, so the API serves sample data and the frontend works with no database.
To use Tiger, put the connection string in `PLANIT_DATABASE_URL`, run `make migrate`, and set `PLANIT_MOCK=0`.

## Layout

| Path | What | Owner |
|---|---|---|
| `db/migrations/` | Database schema (Tiger Data: Postgres + TimescaleDB + PostGIS) | Both |
| `backend/planit/models.py` | **API contract**: every JSON shape | Both |
| `backend/planit/api/` | FastAPI routes; `mock.py` has the sample data | Person B |
| `backend/planit/worker/` | Data ingestion, hazard rules, briefings | Person A |
| `backend/planit/ml/` | Hazard model: features, training, scoring | Person A |
| `frontend/` | Next.js app: dashboard, site page, crew reports, briefings | Person B |
| `docs/` | Architecture, API contract, workflow | Both |

Read next: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/API.md](docs/API.md), [docs/WORKFLOW.md](docs/WORKFLOW.md).
