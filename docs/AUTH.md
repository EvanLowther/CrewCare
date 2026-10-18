# Login, roles and site membership

Auth0 proves who someone is. Their **role** and **which sites they're on** live in Tiger (`users`,
`site_members`, migration `006_auth.sql`), and the admin changes them from the app.

## Roles

| Role | Who | Gets it how |
|---|---|---|
| `admin` | Project owners | Their Auth0-verified email is in `PLANIT_ADMIN_EMAILS`, or another admin promotes them |
| `manager` | Site leads | An admin promotes them on the Admin page |
| `crew` | Field workers | Everyone who signs up starts here |

Per site, a member is that site's `manager` or `crew`. Only users with the manager (or admin) role can be a
site's manager. Demoting a manager to crew makes them crew on the sites they managed.

## Sites

- **Reference sites** (`sites.is_reference`, the EIA plants from `scripts/load_sites.py`) are public: anyone, even
  signed out, sees them, their alerts, briefings and crew reports. They can't report on one unless an admin adds
  them to it.
- **Private sites** are the ones managers create (name, map pin, description; state and timezone come from the pin).
  Only their members and admins see them. New ids start at 9,000,000, above any EIA plant code. The worker picks
  them up on its next poll.

## Who may do what

| | Signed out | Crew | Manager | Admin |
|---|---|---|---|---|
| See reference sites (map, pages, alerts, briefings, reports) | Yes | Yes | Yes | Yes |
| See private sites | — | Ones they're on | Ones they're on | All |
| Report a hazard | — | On their sites, phone GPS **and** pin within 5 mi | Same | Any site, anywhere |
| Create a site | — | — | Yes (becomes its manager) | Yes |
| Edit a site, add/remove members, resolve reports | — | — | On sites they manage | Any |
| Delete a site | — | — | Ones they created and still manage | Any |
| Admin page: users, roles | — | — | — | Yes |
| Generate tomorrow's briefings now | — | — | Sites they manage | Every site |
| Demo buttons (lightning replay) | — | — | — | Yes |

The rules are plain functions in `backend/planit/api/access.py` (tested in `tests/test_access.py`). The 5-mile
check runs on the server, but a browser can't prove its GPS isn't faked: it stops mistakes, not a determined cheat.

## How a request is checked

1. The website signs people in with Auth0 (`@auth0/nextjs-auth0`, email + password and Google) and sends the
   Auth0 access token as `Authorization: Bearer <token>` on `/api/*` calls.
2. FastAPI (`backend/planit/auth.py`) checks the token's signature against Auth0's keys, its expiry, issuer and
   audience, then finds the `users` row by the token's `sub`. The first time it sees someone, it asks Auth0's
   `/userinfo` for their name and email and creates the row.
3. No `Authorization` header = signed out (reference sites only).
4. Photo URLs carry a signature (`?exp=&sig=`) because `<img>` tags can't send the token.

## Local development: "Sign in as"

`PLANIT_AUTH_DEV=1` (laptops and CI only, never on the server) makes the API accept
`Authorization: Dev <admin|manager|manager2|crew|crew2>`. The website shows a "Sign in as" menu instead of the
Auth0 button. Dev users are stored with `dev|` ids; the live server rejects them and hides them from searches and
the Admin page. Backend tests run this way with mock data (`tests/conftest.py`).

## Settings

| Variable | Where | What |
|---|---|---|
| `PLANIT_AUTH0_DOMAIN` | API | e.g. `planit-control.us.auth0.com` |
| `PLANIT_AUTH0_AUDIENCE` | API | The Auth0 API identifier, e.g. `https://api.planit-control` |
| `PLANIT_ADMIN_EMAILS` | API | Comma-separated; always admin once Auth0 has verified the email |
| `PLANIT_PHOTO_SIGNING_KEY` | API | Random secret for photo links (server only) |
| `PLANIT_AUTH_DEV` | API | `1` on laptops for "Sign in as"; unset on the server |
| `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_SECRET`, `APP_BASE_URL`, `AUTH0_AUDIENCE` | Website | Auth0 Next.js SDK; callback `https://<host>/auth/callback` |

## API

| Method | Path | Who |
|---|---|---|
| GET | `/api/me` | Anyone (`user` is null when signed out) |
| POST | `/api/sites` | Managers, admins |
| PATCH / DELETE | `/api/sites/{id}` | Site managers, admins (delete: creator or admin) |
| GET / POST | `/api/sites/{id}/members` | Members see; site managers and admins add |
| DELETE | `/api/sites/{id}/members/{user_id}` | Site managers, admins |
| GET | `/api/users?q=` | Managers, admins (find people to add) |
| PATCH | `/api/reports/{id}/resolve` | Site managers, admins |
| GET / PATCH | `/api/admin/users`, `/api/admin/users/{id}` | Admins |
