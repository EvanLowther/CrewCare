# Workflow

## Branches and PRs
- `main` always runs, and every merge to it deploys to the Vultr server (site, API and worker) and applies new
  migrations. Never push broken code to it.
- One branch per task: `a/<name>` for Person A, `b/<name>` for Person B. Two sessions at once: give the second its
  own worktree (`git worktree add ../planit-control-<name> -b a/<name> main`).
- Before pushing, run the quick checks for what you changed (`ruff check .` and the related `pytest` files, or
  `pnpm lint` + `tsc`), then open the PR and merge it; no need to wait for CI. CI (about 1-2 min) still runs on the
  PR and on `main`: if it goes red, fix it next. GitHub deletes the branch on merge.
- CI skips Markdown-only changes. The slow Windows setup check runs only when setup files change (`dev.py`,
  `pyproject.toml`, `package.json`, the lockfile, the `.env` examples).
- Tick an item here in the PR that finishes it, then move it to "Already done".

## Who touches what
| Area | Person A | Person B |
|---|---|---|
| `backend/planit/worker/`, `backend/planit/ml/`, `backend/scripts/` | ✅ | |
| `backend/planit/api/`, `frontend/` | | ✅ |
| `backend/planit/models.py`, `db/migrations/` | heads-up first | heads-up first |

## To do

### Together
- [ ] Full demo run on the hosted site with real data: dashboard (both models), a site page, alerts, briefings,
      adding a site as a manager (scores within a minute), a crew report from a phone, admin
- [ ] Decide the rest of the national alert types (`winter`, `cold`, `landslide`): NWS winter and cold warnings
      still arrive as `nws`. Needs `AlertType` in models.py, the alerts CHECK and frontend icons together
- [ ] Feature freeze, bug fixes
- [ ] Refresh the demo data, record a backup video, README + pitch, rehearse
- [ ] Fill in the README's Auth0 and Gemini rows in the tools table
- [ ] Put the Gemini key on the server (`PLANIT_GEMINI_API_KEY` in `/opt/planit/.env`, then
      `systemctl restart planit-worker planit-api`); until then every briefing is the template

### Person A (data + ML)
- [ ] Lightning stop-work, live: merge `a/lightning` (the rule, 30-minute countdown and replay; rebase on `main` and
      renumber its `006_simulated_weather.sql` to `010`), then feed it real strikes from GOES GLM (NOAA, free,
      ~20 s delay). `worker/rules/lightning.py` on `main` is still a stub, so no site gets a lightning alert today
- [ ] Crew reports raise the score: an active report near a site (downed line, flooding, heat illness, ...) becomes
      a hazard in both scores, like fire and quake alerts do

Later, only if there's time: a river flood rule with NWS flood stages for sites on big rivers (NWS Flood Warnings
already reach both scores).

### Person B (app)
- [ ] Demo buttons in the app for admins: lightning replay (`POST /api/demo/lightning-replay` exists), then flood
- [ ] Test the report form on a phone on the hosted URL (camera, GPS)
- [ ] `mock.py` sample sites across the country and timezones (it still has 12 Florida sites); contract tests pass
- [ ] Map: marker clustering; Alaska and Hawaii reachable
- [ ] `?state=` on `/api/sites` and `/api/alerts`; state and hazard filters on the ranked list

## Already done

**Data and scoring (Person A)**
- 160 power plants from EIA-860M in all 50 states, timezones by location (#3, #21)
- Weather history from Open-Meteo, NOAA Storm Events labels for every state, the live Open-Meteo + NWS pollers, one
  national NWS alerts request every 2 min (#5-#7, #21)
- National XGBoost model with a test bench and region comparison; newest model loaded automatically (#9, #10, #12,
  #13, #21, #23, #24)
- rules-v2 Real-time scorer: heat, cold, fog, storms, wind, rain, ground, snow, ice and NWS alerts, each with a
  recommended action (#17, #22)
- Both scorers side by side; Predictive on the Real-time 0-10 scale with floors at NWS warnings (#15, #29)
- Wildfire (NIFC), smoke (PM2.5 air quality) and earthquakes (USGS) in both scorers (#31)
- 6 PM next-day briefing per site in its own timezone: facts from the scores, forecasts, smoke and alerts; Gemini
  writes the summary, the template covers it without a key
- `job_requests` so demo buttons reach the worker through the database (#14)
- New or moved sites get set up at once (`site_setup` job): NWS grid and zones, 5 days of Open-Meteo history,
  air quality, alerts and both scores within about a minute; the national model needs no retraining for them
- Fire weather rule (dry air x wind after 3 dry days, up to 4.5) in both scorers; Predictive spreads calm days below
  1.0 by the model's odds instead of scoring a quarter of all days exactly 0

**App (Person B)**
- Real sites, site detail, alerts and reports queries (#4)
- Dashboard map and ranked list, Real-time / Predictive switch, site page with top factors and actions, lightning
  banner with countdown, alerts feed (#1, #11, #16, #28); the forecast-hour slider was removed again
- Crew report form with live GPS and a draggable pin (#18)
- Login and roles with Auth0: admin / manager / crew, private sites, site management, admin page (#25, #27)
- Address search for new sites; maps survive navigating back; Real-time is the default view (#30)
- Hosted on Vultr over HTTPS, auto-deploying `main` (#19, #20)
- Briefings API (private sites stay private) and page: tomorrow or today, riskiest first, "Generate now" for admins
- Icons and colours per hazard kind (heat, cold, snow/ice, smoke, wildfire, earthquake, ...) on factors and alerts;
  17 crew report types (lightning, ice, snow, cold stress, smoke, sinkhole, fallen tree, gas leak, quake damage, ...);
  alerts disappear the moment they end; deleting a site works again; no more "Can't reach the API" during deploys
