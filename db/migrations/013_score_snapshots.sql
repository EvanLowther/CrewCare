-- Every 5-minute score, not just the last one each hour. The worker upserts one hazard_scores row per site, hour
-- and scorer, so each pass overwrites the hour's score and the ups and downs within an hour were lost. This trigger
-- copies each pass's current-hour score here, so the site page can chart how it moved (planit/api/queries.py).
-- Kept 14 days.

CREATE TABLE score_snapshots (
    site_id   integer      NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    scorer    text         NOT NULL,               -- 'rules' (Real-time) or 'ml' (Predictive)
    ts        timestamptz  NOT NULL,               -- when it was scored
    score     numeric(3,1) NOT NULL,
    level     text         NOT NULL,
    PRIMARY KEY (site_id, scorer, ts)
);
SELECT create_hypertable('score_snapshots', 'ts', chunk_time_interval => interval '1 day');
SELECT add_retention_policy('score_snapshots', interval '14 days');

CREATE FUNCTION snapshot_score() RETURNS trigger AS $$
BEGIN
    INSERT INTO score_snapshots (site_id, scorer, ts, score, level)
    VALUES (NEW.site_id, NEW.scorer, NEW.computed_at, NEW.score, NEW.level)
    ON CONFLICT DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER hazard_scores_snapshot AFTER INSERT OR UPDATE ON hazard_scores
    FOR EACH ROW WHEN (NEW.kind = 'current') EXECUTE FUNCTION snapshot_score();
