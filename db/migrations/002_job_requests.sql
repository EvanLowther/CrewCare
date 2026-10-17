-- Demo buttons -> worker. The API and the worker never call each other, so a button (lightning replay,
-- "Generate briefings now") inserts a row here and the worker's `jobs` poller (every 2 s) claims and runs it.

CREATE TABLE job_requests (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind          text        NOT NULL CHECK (kind IN ('lightning_replay', 'generate_briefings')),
    params        jsonb       NOT NULL DEFAULT '{}'::jsonb,   -- e.g. {"site_id": 621, "strikes": 6, ...}
    status        text        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'failed')),
    error         text,
    requested_at  timestamptz NOT NULL DEFAULT now(),
    started_at    timestamptz,
    finished_at   timestamptz
);
CREATE INDEX job_requests_pending_idx ON job_requests (requested_at) WHERE status = 'pending';
