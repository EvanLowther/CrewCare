-- A site a manager just created (or moved) gets its weather and both scores right away instead of on the next
-- regular polls (worker/site_setup.py): the API queues a 'site_setup' job request with {"site_id"}.

ALTER TABLE job_requests DROP CONSTRAINT job_requests_kind_check;
ALTER TABLE job_requests ADD CONSTRAINT job_requests_kind_check CHECK (kind IN
    ('lightning_replay', 'generate_briefings', 'site_setup'));
