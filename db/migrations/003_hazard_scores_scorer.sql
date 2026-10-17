-- Keep both scorers' results side by side, so the dashboard can switch between rules-v1 and the ML model.
-- One row per (site, hour, kind, scorer); model_version still says which version of that scorer wrote it.

ALTER TABLE hazard_scores
    ADD COLUMN scorer text NOT NULL DEFAULT 'rules' CHECK (scorer IN ('rules', 'ml'));

UPDATE hazard_scores SET scorer = 'ml' WHERE model_version LIKE 'xgb-%';

ALTER TABLE hazard_scores DROP CONSTRAINT hazard_scores_pkey;
ALTER TABLE hazard_scores ADD PRIMARY KEY (site_id, ts, kind, scorer);
