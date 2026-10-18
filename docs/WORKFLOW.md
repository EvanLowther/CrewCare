# Workflow

## Branches and PRs
- `main` always runs, and every merge to it deploys to the Vultr server (site, API and worker) and applies new
  migrations. Never push broken code to it.
- One branch per task: `a/<name>` for Person A, `b/<name>` for Person B. Two sessions at once: give the second its
  own worktree (`git worktree add ../planit-control-<name> -b a/<name> main`).
- Open a PR, let CI pass, merge, then pull `main`. GitHub deletes the branch on merge.
- Tick an item here in the PR that finishes it, then move it to "Already done".

## Who touches what
| Area | Person A | Person B |
|---|---|---|
| `backend/planit/worker/`, `backend/planit/ml/`, `backend/scripts/` | ✅ | |
| `backend/planit/api/`, `frontend/` | | ✅ |
| `backend/planit/models.py`, `db/migrations/` | heads-up first | heads-up first |

## To do

### Together
- [ ] Full demo run on the hosted site with real data: dashboard (both models, hour slider), a site page, alerts,
      a crew report from a phone, admin
- [ ] Decide the rest of the national alert types (`winter`, `cold`, `landslide`): NWS winter and cold warnings
      still arrive as `nws`. Needs `AlertType` in models.py, the alerts CHECK and frontend icons together
- [ ] Feature freeze, bug fixes
- [ ] Refresh the demo data, record a backup video, README + pitch, rehearse
- [ ] Fill in the README's Auth0 and Gemini rows in the tools table

### Person A (data + ML)
- [ ] Merge `a/lightning`: lightning stop-work rule, 30-minute countdown, replay, and the `simulate` demo script
      (lightning, hurricane, flood, blizzard). Rebase on `main` and renumber its `006_simulated_weather.sql` to
      `008` (006 is taken by auth). `worker/rules/lightning.py` on `main` is still a stub, so the demo button's
      replay does nothing yet
- [ ] Merge `a/briefings`: the 6 PM next-day briefing job (Gemini, template fallback), for every US timezone.
      `worker/briefing/generate.py` on `main` is still a stub
- [ ] River flood rule with NWS flood stages; must cover the Mississippi (`ingest/usgs.py` and `rules/flood.py`
      are stubs)
- [ ] Crew reports raise the score
- [ ] Flood replay demo, like the lightning one
- [ ] Wildfire: NASA FIRMS satellite detections (sooner than NIFC's reports) and NIFC fire perimeters; debris flow
      below burn scars
- [ ] Live lightning strikes (GOES GLM) after the replay works
- [ ] Later: score baseline per region, if "5" should mean "unusual for this site"; separate models per hazard
      (storm, winter, flood, heat) instead of one "hazard day" model

### Person B (app)
- [ ] Real `GET /api/briefings` and `POST /api/briefings/generate` (both return "not built" outside mock mode),
      then the briefings page on real data with "Generate now" (it's an empty placeholder now)
- [ ] Demo buttons in the app for admins: lightning replay (`POST /api/demo/lightning-replay` exists), then flood
- [ ] Test the report form on a phone on the hosted URL (camera, GPS)
- [ ] `mock.py` sample sites across the country and timezones (it still has 12 Florida sites); contract tests pass
- [ ] Map: marker clustering; Alaska and Hawaii reachable
- [ ] `?state=` on `/api/sites` and `/api/alerts`; state and hazard filters on the ranked list
- [ ] Icons and colours for factor kinds (smoke, wildfire, earthquake, winter, cold, ...) where factors are listed
- [ ] Crew report types for national hazards (ice, smoke, snakes/bears, sinkhole, ...)

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
- `job_requests` so demo buttons reach the worker through the database (#14)

**App (Person B)**
- Real sites, site detail, alerts and reports queries (#4)
- Dashboard map and ranked list, Real-time / Predictive switch, forecast-hour slider, site page with top factors
  and actions, lightning banner with countdown, alerts feed (#1, #11, #16, #28)
- Crew report form with live GPS and a draggable pin (#18)
- Login and roles with Auth0: admin / manager / crew, private sites, site management, admin page (#25, #27)
- Address search for new sites; maps survive navigating back; Real-time is the default view (#30)
- Hosted on Vultr over HTTPS, auto-deploying `main` (#19, #20)
