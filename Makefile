# PlanIT Control. Run `make setup` once, then `make api` and `make web` in two terminals.
PY := backend/.venv/bin/python

.PHONY: setup api web worker migrate types test lint

setup:            ## Install backend + frontend dependencies
	cd backend && python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -e ".[dev,ml]"
	cd frontend && pnpm install
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")
	@test -f frontend/.env.local || cp frontend/.env.example frontend/.env.local

api:              ## FastAPI on http://localhost:8000 (docs at /docs)
	cd backend && .venv/bin/uvicorn planit.api.main:app --reload --port 8000

web:              ## Next.js on http://localhost:3000
	cd frontend && pnpm dev

worker:           ## Background data jobs (Person A)
	cd backend && .venv/bin/python -m planit.worker.main

migrate:          ## Apply db/migrations to Tiger
	cd backend && .venv/bin/python scripts/migrate.py

types:            ## Regenerate frontend types after changing backend/planit/models.py
	PLANIT_MOCK=1 $(PY) -c "import json; from planit.api.main import app; print(json.dumps(app.openapi(), indent=2))" > docs/openapi.json
	cd frontend && pnpm exec openapi-typescript ../docs/openapi.json -o src/lib/api-types.ts

test:             ## Backend contract tests + frontend type check
	cd backend && .venv/bin/pytest -q
	cd frontend && pnpm exec tsc --noEmit

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && pnpm lint
