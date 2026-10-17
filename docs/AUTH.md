# Login with Auth0 (plan, not built yet)

Today the site is public: anyone with the link can view it and post crew reports. This is the plan for adding
Auth0 login and two roles without reworking the app.

## Roles

| Role | Who | Can |
|---|---|---|
| `crew` | Field workers | Report hazards; see alerts, the map and their sites' briefings |
| `supervisor` | Site and safety leads | Everything crew can, plus the ranked dashboard, model switch, "Generate briefings now" and the lightning demo; resolve crew reports |

Roles are Auth0 **Roles** (RBAC), added to the access token as permissions:
`reports:create`, `reports:resolve`, `briefings:generate`, `demo:run`.

## Pages

| Page | Logged out | crew | supervisor |
|---|---|---|---|
| `/` dashboard | login screen | map + alerts, read only | full dashboard |
| `/sites/[id]` | login screen | yes | yes |
| `/alerts` | login screen | yes | yes |
| `/briefings` | login screen | read | read + Generate now |
| `/report` | login screen | yes | yes |

## API routes

| Route | Needs |
|---|---|
| `GET /api/health` | nothing (uptime checks) |
| `GET /api/sites`, `/api/sites/{id}`, `/api/alerts`, `/api/briefings`, `/api/reports`, `/api/photos/{id}` | any logged-in user |
| `POST /api/reports` | `reports:create` (and the reporter's name comes from the token, not the form) |
| `POST /api/briefings/generate` | `briefings:generate` |
| `POST /api/demo/lightning-replay` | `demo:run` |

## How it plugs in

- **Frontend:** `@auth0/nextjs-auth0` (v4) with `proxy.ts` (Next 16's middleware) to require a session on every page
  except `/auth/*`. The server forwards the user's access token to FastAPI on `/api/*` calls.
- **Backend:** one FastAPI dependency in `planit/api/deps.py` that checks the token against Auth0's JWKS
  (audience = the PlanIT API), and `require("reports:create")` on the write routes.
- **Database:** a `users` table isn't needed; `hazard_reports.reporter_name` gets the token's name, and a new
  migration can add `reporter_sub` later.
- **Config:** `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_SECRET`, `APP_BASE_URL` (frontend) and
  `PLANIT_AUTH0_DOMAIN`, `PLANIT_AUTH0_AUDIENCE` (backend), all in the server's `.env` only. Callback URL:
  `https://<hostname>/auth/callback`.
- **Demo:** two test users in Auth0 (one crew, one supervisor) so judges can see both views.
