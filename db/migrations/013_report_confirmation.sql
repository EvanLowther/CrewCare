-- A site manager (or admin) can confirm a crew report (PATCH /api/reports/{id}/confirm). Confirmed reports count in the
-- score at full weight, and a high one of any type can reach "extreme" (see hazards.crew_report). Weather data
-- confirms reports on its own at score time; this records the human confirmation.
ALTER TABLE hazard_reports
    ADD COLUMN confirmed_by uuid REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN confirmed_at timestamptz;

-- River gauges (012): tailwater gauges below locks and dams (SHEF HT) count as rivers now, so look again for the sites
-- that found no gauge (e.g. Prairie Island, MN, below Mississippi Lock & Dam 3).
UPDATE sites SET river_checked_at = NULL WHERE usgs_gauge_id IS NULL;
