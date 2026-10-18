# Contributing

Read [README.md](README.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/API.md](docs/API.md) and
[docs/WORKFLOW.md](docs/WORKFLOW.md) before changing anything. Branches, PRs and who owns which part of the code are
in WORKFLOW.md.

- The worker and API only share the database; they never import each other's routes or jobs.
- `backend/planit/models.py` is the API contract. After changing it, run `python dev.py types` and update
  `backend/planit/api/mock.py`.
- Schema changes go in a new numbered file in `db/migrations/`; never edit a migration that has been applied.
- The frontend uses Next.js 16, which differs from older versions: read route params and other runtime data inside
  `<Suspense>`, and check `frontend/node_modules/next/dist/docs/` when an API looks unfamiliar.
- Run `python dev.py test` and `python dev.py lint` before committing.
