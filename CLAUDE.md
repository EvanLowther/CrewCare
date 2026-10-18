# Crew Care

Read README.md, docs/ARCHITECTURE.md, docs/API.md and docs/WORKFLOW.md before changing anything.

- The worker and API only share the database; they never import each other's routes or jobs.
- `backend/planit/models.py` is the API contract. After changing it run `python dev.py types` and update `mock.py`.
- Schema changes go in a new numbered file in `db/migrations/`; never edit an applied migration.
- The frontend uses Next.js 16 (see frontend/AGENTS.md): read params and runtime data inside `<Suspense>`.
- Run `python dev.py test` and `python dev.py lint` before committing.
