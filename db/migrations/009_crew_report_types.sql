-- Crew report types for hazards across the country, not just Florida (models.py HazardType). Existing reports keep
-- their types; 'wildlife' now also covers snakes, bears and the like.
ALTER TABLE hazard_reports DROP CONSTRAINT hazard_reports_hazard_type_check;
ALTER TABLE hazard_reports ADD CONSTRAINT hazard_reports_hazard_type_check CHECK (hazard_type IN (
    'wildlife', 'flooding', 'unstable_ground', 'downed_line', 'heat_illness', 'fire', 'other',
    'lightning', 'high_wind', 'ice', 'snow', 'cold_stress', 'smoke', 'sinkhole', 'fallen_tree', 'gas_leak',
    'earthquake_damage'));
