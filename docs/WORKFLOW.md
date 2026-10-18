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

What's left, measured against the Sperry Tech brief (`.github/sperry tech.pdf`). ⭐ = the brief asks for it by name.

### Together
- [ ] Check Gemini on the hosted site: press "Generate now" on Briefings as an admin; they should say "Gemini"
- [ ] Full demo run on the hosted site with real data: dashboard (both models), a site page, alerts, briefings,
      adding a site as a manager, a crew report from a phone, admin
- [ ] Feature freeze, bug fixes
- [ ] Refresh the demo data, record a backup video, README + pitch, rehearse
- [ ] Fill in the README's Auth0 row in the tools table

### Person A (worker + ML)
- [x] ⭐ Lightning stop-work, live: the rule from `a/lightning` (stop work for any flash within 10 mi, a 30-minute
      all-clear that restarts with each strike, replay) fed by GOES GLM every 20 s (`ingest/glm.py`)
- [x] ⭐ River flood-risk warning: sites within 2 mi of an NWS river gauge with flood stages get a `flood` alert when
      the river is at or forecast to reach action stage, or after 1 in of rain in 12 h (NOAA NWPS, every 15 min)
- [ ] ⭐ Crew reports in the risk picture: an active report near a site (wildlife, downed line, flooding, heat
      illness, ...) becomes a hazard in both scores, like fire and quake alerts, and a `crew_report` alert for that
      site so its team hears about it (the alert type exists; nothing creates it yet)

### Person B (API + app)
- [ ] Demo buttons for admins: lightning replay (`POST /api/demo/lightning-replay` exists) once lightning is merged
- [ ] Test the report form on a phone on the hosted URL (camera, GPS)
- [ ] If there's time: map marker clustering with Alaska and Hawaii in view; state and hazard filters on the
      ranked list; `mock.py` sample sites across the country

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
- Notifications for each site's members: crew reports, danger alerts and the 6 PM briefing, live within ~2 s as
  pop-ups on every page, a bell inbox, and push to phones and browsers (Android/desktop; iPhone from the Home
  Screen). A `crew_report` alert with `meta.report_id` shares its report's notification (no double ping)
- My sites page: the sites you're on (admins: any site), each one's crew reports active then past; managers
  manage the site and resolve reports there. Report hazard stays in the top bar
- Past hazards on the site page and new-site form: crew reports within 5 mi (resolved too) and NOAA Storm Events
  within 25 mi
- Icons and colours per hazard kind (heat, cold, snow/ice, smoke, wildfire, earthquake, ...) on factors and alerts;
  17 crew report types (lightning, ice, snow, cold stress, smoke, sinkhole, fallen tree, gas leak, quake damage, ...);
  alerts disappear the moment they end; deleting a site works again; no more "Can't reach the API" during deploys
