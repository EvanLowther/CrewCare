-- National scope: sites in every state (scripts/load_sites.py), and snow for the cold and winter hazards that
-- Florida never needed. Open-Meteo reports snowfall in inches and snow depth in feet with precipitation_unit=inch.

ALTER TABLE weather
    ADD COLUMN snowfall_in   real,                 -- snow that fell during this hour
    ADD COLUMN snow_depth_ft real;                 -- snow on the ground

ALTER TABLE sites ALTER COLUMN state DROP DEFAULT;  -- every site now says its own state
CREATE INDEX sites_state_idx ON sites (state);
