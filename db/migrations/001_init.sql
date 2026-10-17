-- PlanIT Control: initial schema
-- Owner: both. Changes to this file need a heads-up to the other person.
-- Apply with: make migrate  (runs backend/scripts/migrate.py)

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Sites: the ~60 Florida power plants from EIA-860M
-- ---------------------------------------------------------------------------
CREATE TABLE sites (
    id              integer PRIMARY KEY,           -- EIA plant code
    name            text        NOT NULL,
    utility         text,
    county          text,
    state           text        NOT NULL DEFAULT 'FL',
    plant_type      text,                          -- EIA primary technology, e.g. 'Natural Gas Fired Combined Cycle'
    capacity_mw     numeric(8,1),
    latitude        double precision NOT NULL,
    longitude       double precision NOT NULL,
    geom            geography(Point, 4326) NOT NULL,
    -- Florida panhandle west of the Apalachicola River is Central time.
    -- The 6 PM briefing is per site local time, so this matters.
    timezone        text        NOT NULL DEFAULT 'America/New_York',
    usgs_gauge_id   text,                          -- nearest river gauge, if the site is on a river
    flood_zone      text,                          -- FEMA zone, optional
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sites_geom_idx ON sites USING gist (geom);

-- ---------------------------------------------------------------------------
-- Weather: hourly observations and forecasts per site (Open-Meteo)
-- ---------------------------------------------------------------------------
CREATE TABLE weather (
    site_id          integer     NOT NULL REFERENCES sites(id),
    ts               timestamptz NOT NULL,         -- the hour this reading applies to
    is_forecast      boolean     NOT NULL,
    temp_f           real,
    heat_index_f     real,                         -- Open-Meteo apparent_temperature
    humidity_pct     real,
    precip_in        real,                         -- precipitation during this hour
    precip_prob_pct  real,
    wind_mph         real,
    gust_mph         real,
    cape_jkg         real,                         -- thunderstorm potential
    soil_moisture    real,                         -- m3/m3, 0-7 cm layer
    weather_code     smallint,                     -- WMO code
    updated_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (site_id, ts, is_forecast)
);
SELECT create_hypertable('weather', 'ts', chunk_time_interval => interval '7 days');

-- Daily rollup of observed weather: ML features and the dashboard "last 24h" stats.
CREATE MATERIALIZED VIEW weather_daily
WITH (timescaledb.continuous) AS
SELECT
    site_id,
    time_bucket('1 day', ts) AS day,
    max(heat_index_f)   AS max_heat_index_f,
    max(temp_f)         AS max_temp_f,
    sum(precip_in)      AS total_precip_in,
    max(gust_mph)       AS max_gust_mph,
    max(cape_jkg)       AS max_cape_jkg,
    avg(soil_moisture)  AS avg_soil_moisture
FROM weather
WHERE NOT is_forecast
GROUP BY site_id, time_bucket('1 day', ts)
WITH NO DATA;

SELECT add_continuous_aggregate_policy('weather_daily',
    start_offset      => interval '3 days',
    end_offset        => interval '1 hour',
    schedule_interval => interval '1 hour');

-- ---------------------------------------------------------------------------
-- River gauges and levels (USGS), for flood warnings
-- ---------------------------------------------------------------------------
CREATE TABLE river_gauges (
    gauge_id         text PRIMARY KEY,             -- USGS site number
    name             text NOT NULL,
    river            text,
    latitude         double precision,
    longitude        double precision,
    action_stage_ft  real,
    flood_stage_ft   real                          -- from NWS, may be null
);

CREATE TABLE river_levels (
    gauge_id   text        NOT NULL REFERENCES river_gauges(gauge_id),
    ts         timestamptz NOT NULL,
    stage_ft   real,
    flow_cfs   real,
    PRIMARY KEY (gauge_id, ts)
);
SELECT create_hypertable('river_levels', 'ts', chunk_time_interval => interval '7 days');

ALTER TABLE sites
    ADD CONSTRAINT sites_usgs_gauge_fk FOREIGN KEY (usgs_gauge_id) REFERENCES river_gauges(gauge_id);

-- ---------------------------------------------------------------------------
-- Lightning strikes (replay, simulator, or live feed)
-- ---------------------------------------------------------------------------
CREATE TABLE lightning_strikes (
    id              bigint GENERATED ALWAYS AS IDENTITY,
    ts              timestamptz NOT NULL,
    latitude        double precision NOT NULL,
    longitude       double precision NOT NULL,
    geom            geography(Point, 4326) NOT NULL,
    source          text NOT NULL CHECK (source IN ('replay', 'simulator', 'glm', 'blitzortung')),
    peak_current_ka real,
    replay_run_id   uuid,                          -- groups strikes from one replay run
    PRIMARY KEY (id, ts)
);
SELECT create_hypertable('lightning_strikes', 'ts', chunk_time_interval => interval '1 day');
CREATE INDEX lightning_strikes_geom_idx ON lightning_strikes USING gist (geom);

-- ---------------------------------------------------------------------------
-- Raw NWS alerts, matched to sites by point lookup
-- ---------------------------------------------------------------------------
CREATE TABLE nws_alerts (
    alert_id     text        NOT NULL,             -- NWS id (urn:oid:...)
    site_id      integer     NOT NULL REFERENCES sites(id),
    event        text        NOT NULL,             -- e.g. 'Flood Warning', 'Heat Advisory'
    severity     text,                             -- Extreme / Severe / Moderate / Minor / Unknown
    headline     text,
    description  text,
    onset        timestamptz,
    ends         timestamptz,
    fetched_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (alert_id, site_id)
);

-- ---------------------------------------------------------------------------
-- App alerts: what crews and supervisors actually see
-- ---------------------------------------------------------------------------
CREATE TABLE alerts (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id       integer     NOT NULL REFERENCES sites(id),
    type          text        NOT NULL CHECK (type IN
                    ('lightning', 'flood', 'heat', 'storm', 'wind', 'wildfire', 'crew_report', 'nws')),
    severity      text        NOT NULL CHECK (severity IN ('info', 'warning', 'danger')),
    title         text        NOT NULL,
    message       text        NOT NULL,
    status        text        NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cleared')),
    started_at    timestamptz NOT NULL DEFAULT now(),
    -- Lightning: last strike within 10 mi + 30 min. Pushed forward on every new strike.
    all_clear_at  timestamptz,
    cleared_at    timestamptz,
    -- Keeps one active alert per site per thing, e.g. 'lightning' or an NWS alert id.
    dedupe_key    text        NOT NULL,
    -- Type-specific extras, e.g. {"strike_count": 4, "nearest_strike_mi": 3.2}
    meta          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX alerts_one_active_idx ON alerts (site_id, type, dedupe_key) WHERE status = 'active';
CREATE INDEX alerts_updated_idx ON alerts (updated_at);

-- ---------------------------------------------------------------------------
-- Hazard scores (0-10) from the ML model or the rule-based fallback
-- ---------------------------------------------------------------------------
CREATE TABLE hazard_scores (
    site_id        integer     NOT NULL REFERENCES sites(id),
    ts             timestamptz NOT NULL,           -- the hour the score applies to
    kind           text        NOT NULL CHECK (kind IN ('current', 'forecast')),
    score          numeric(3,1) NOT NULL CHECK (score BETWEEN 0 AND 10),
    level          text        NOT NULL CHECK (level IN ('low', 'moderate', 'high', 'extreme')),
    -- Top contributing factors: [{"key": "heat_index", "label": "Heat index 112°F", "contribution": 2.4}]
    factors        jsonb       NOT NULL DEFAULT '[]'::jsonb,
    model_version  text        NOT NULL,           -- e.g. 'rules-v1', 'xgb-2026-10-17'
    computed_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (site_id, ts, kind)
);
SELECT create_hypertable('hazard_scores', 'ts', chunk_time_interval => interval '7 days');

-- ---------------------------------------------------------------------------
-- Crew hazard reports and their photos
-- ---------------------------------------------------------------------------
CREATE TABLE photos (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    content_type  text    NOT NULL,                -- always image/jpeg after resizing
    data          bytea   NOT NULL,                -- resized to <= 1600 px, ~500 KB max
    width         integer NOT NULL,
    height        integer NOT NULL,
    size_bytes    integer NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE hazard_reports (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id        integer REFERENCES sites(id),   -- nearest site, set by the API
    latitude       double precision NOT NULL,
    longitude      double precision NOT NULL,
    geom           geography(Point, 4326) NOT NULL,
    hazard_type    text NOT NULL CHECK (hazard_type IN
                     ('wildlife', 'flooding', 'unstable_ground', 'downed_line', 'heat_illness', 'fire', 'other')),
    severity       text NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    description    text,
    reporter_name  text,
    photo_id       uuid REFERENCES photos(id),
    status         text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'resolved')),
    created_at     timestamptz NOT NULL DEFAULT now(),
    expires_at     timestamptz                    -- e.g. wildlife sighting fades after 48 h
);
CREATE INDEX hazard_reports_geom_idx ON hazard_reports USING gist (geom);
CREATE INDEX hazard_reports_site_idx ON hazard_reports (site_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- 6 PM next-day safety briefings
-- ---------------------------------------------------------------------------
CREATE TABLE briefings (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id       integer NOT NULL REFERENCES sites(id),
    for_date      date    NOT NULL,                -- the work day being briefed (tomorrow)
    summary       text    NOT NULL,                -- one-paragraph plain English
    -- Structured detail: {"peak_heat_index_f": 108, "storm_window": "2-6 PM", "recommendations": [...]}
    details       jsonb   NOT NULL DEFAULT '{}'::jsonb,
    generated_by  text    NOT NULL,                -- 'gemini-...' or 'template'
    generated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (site_id, for_date)
);

-- ---------------------------------------------------------------------------
-- ML training data: NOAA Storm Events (Florida, a few years)
-- ---------------------------------------------------------------------------
CREATE TABLE storm_events (
    event_id     bigint PRIMARY KEY,
    event_type   text        NOT NULL,             -- 'Thunderstorm Wind', 'Lightning', 'Flash Flood', 'Heat', ...
    begin_ts     timestamptz NOT NULL,
    end_ts       timestamptz,
    state        text,
    cz_name      text,                             -- county / zone name
    latitude     double precision,                 -- null for zone-based events
    longitude    double precision,
    injuries     integer,
    deaths       integer,
    damage_usd   bigint
);
CREATE INDEX storm_events_begin_idx ON storm_events (begin_ts);
