# PlanIT Control

Real-time hazard monitoring for utility field crews at ~60 Florida power plant sites (SwampHacks, Sperry Tech challenge).
Combines weather, heat, lightning, flooding, soil saturation and crew hazard reports into one 0-10 risk score per site,
fires stop-work alerts, and sends a 6 PM next-day safety briefing.

## Quick start

### 1. Install the prerequisites (once)

- **Python 3.11+**: https://www.python.org/downloads/. On Windows, tick **"Add python.exe to PATH"** in the installer.
- **Node.js 22 LTS**: https://nodejs.org
- **pnpm**: after Node is installed, run `npm install -g pnpm`

Close and reopen your terminal afterwards so the new commands are found.

### 2. Set up and run

All commands go through `dev.py` and are the same on every OS. Only the Python command differs:
**Windows: `python`** (or `py` if that isn't found) · **macOS: `python3`**.

```
python dev.py setup     # installs everything, creates .env and frontend/.env.local
python dev.py api       # terminal 1: http://localhost:8000/docs
python dev.py web       # terminal 2: http://localhost:3000
```

Run `python dev.py` with no arguments to list every command (`worker`, `migrate`, `types`, `test`, `lint`).

`.env` starts with `PLANIT_MOCK=1`, so the API serves sample data and the frontend works with no database.
To use Tiger, put the connection string in `PLANIT_DATABASE_URL` in `.env`, then set `PLANIT_MOCK=0`.
The schema is already applied to the shared database; `python dev.py migrate` only applies new migration files.

### Windows troubleshooting

- **`python` opens the Microsoft Store or isn't found:** use `py dev.py setup`, or reinstall Python with "Add to PATH" ticked.
- **`pnpm` isn't recognized:** run `npm install -g pnpm`, then open a new terminal.
- **PowerShell says running scripts is disabled** (when calling pnpm): run
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use Command Prompt instead.

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
