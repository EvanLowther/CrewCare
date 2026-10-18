-- River flood-risk warnings (worker/ingest/river.py, worker/rules/flood.py) from NOAA's water prediction service
-- (NWPS). river_gauges.gauge_id and sites.usgs_gauge_id now hold the NWPS gauge id (e.g. 'BTRL1', Mississippi River
-- at Baton Rouge); most NWPS gauges are USGS gauges, whose number goes in usgs_id. flood_stage_ft is NWS "minor".

ALTER TABLE river_gauges
    ADD COLUMN moderate_stage_ft real,
    ADD COLUMN major_stage_ft    real,
    ADD COLUMN usgs_id           text;

ALTER TABLE river_levels
    ADD COLUMN forecast_stage_ft real,             -- highest NWS forecast stage in the next 48 h
    ADD COLUMN category          text;             -- of the observed stage: no_flooding, action, minor, moderate, major

-- When the nearest gauge was looked up; null = not yet (new or moved sites). Sites with no river near stay null in
-- usgs_gauge_id but get a time here, so they aren't looked up on every poll.
ALTER TABLE sites ADD COLUMN river_checked_at timestamptz;
