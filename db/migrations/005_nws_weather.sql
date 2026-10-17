-- Real-time weather from the NWS API (worker/ingest/nws_weather.py): free with no daily cap, so it can be polled
-- every 30 min for every site, and it has fields Open-Meteo doesn't (wind chill, WBGT, visibility, ice).
-- Kept apart from `weather` (Open-Meteo), which the ML model is trained on and weather_daily rolls up.

-- Looked up once per site from https://api.weather.gov/points/{lat},{lon}.
ALTER TABLE sites
    ADD COLUMN nws_grid_id     text,               -- forecast office, e.g. 'BIS'
    ADD COLUMN nws_grid_x      integer,
    ADD COLUMN nws_grid_y      integer,
    ADD COLUMN nws_station     text,               -- nearest observation station, e.g. 'KHZE'
    ADD COLUMN nws_zone        text,               -- forecast zone, e.g. 'NDZ058' (alerts are issued for these)
    ADD COLUMN nws_county_zone text;               -- county zone, e.g. 'NDC055'

CREATE TABLE nws_weather (
    site_id          integer     NOT NULL REFERENCES sites(id),
    ts               timestamptz NOT NULL,         -- the hour this applies to
    is_forecast      boolean     NOT NULL,         -- false: the station observation; true: the gridpoint forecast
    temp_f           real,
    heat_index_f     real,                         -- NWS heat index, null when it doesn't apply
    wind_chill_f     real,                         -- NWS wind chill, null when it doesn't apply
    wbgt_f           real,                         -- wet bulb globe temperature
    humidity_pct     real,
    precip_in        real,                         -- share of the forecast period's total that falls in this hour
    precip_prob_pct  real,
    snowfall_in      real,
    ice_in           real,
    wind_mph         real,
    gust_mph         real,
    visibility_m     real,
    thunder_prob_pct real,
    weather_code     smallint,                     -- WMO code: 95 thunderstorm likely, 45 fog
    updated_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (site_id, ts, is_forecast)
);
SELECT create_hypertable('nws_weather', 'ts', chunk_time_interval => interval '7 days');
