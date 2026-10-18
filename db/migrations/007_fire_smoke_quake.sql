-- Wildfire, smoke and earthquakes (hazards.py smoke / wildfire / earthquake).
-- New app alert types: 'air_quality' (NWS Air Quality Alerts, Dense Smoke Advisories) and 'earthquake' (USGS,
-- worker/ingest/earthquakes.py). 'wildfire' already exists; NIFC fires (worker/ingest/wildfire.py) use it too.

ALTER TABLE alerts DROP CONSTRAINT alerts_type_check;
ALTER TABLE alerts ADD CONSTRAINT alerts_type_check CHECK (type IN
    ('lightning', 'flood', 'heat', 'storm', 'wind', 'wildfire', 'air_quality', 'earthquake', 'crew_report', 'nws'));

-- Hourly air quality per site from the Open-Meteo Air Quality API (worker/ingest/air_quality.py): CAMS model
-- values, observed up to now and forecast after, same layout as `weather`.
CREATE TABLE air_quality (
    site_id       integer     NOT NULL REFERENCES sites(id),
    ts            timestamptz NOT NULL,            -- the hour this applies to
    is_forecast   boolean     NOT NULL,
    us_aqi        real,                            -- US AQI, worst pollutant
    us_aqi_pm2_5  real,                            -- US AQI for PM2.5 alone: smoke, what Cal/OSHA 5141.1 uses
    pm2_5_ugm3    real,                            -- PM2.5 concentration, µg/m³
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (site_id, ts, is_forecast)
);
SELECT create_hypertable('air_quality', 'ts', chunk_time_interval => interval '7 days');
