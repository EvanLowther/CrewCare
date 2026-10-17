-- Login and roles (docs/AUTH.md). Auth0 proves who someone is; their role and site memberships live here.

CREATE TABLE users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth0_sub     text NOT NULL UNIQUE,              -- Auth0 user id, e.g. 'google-oauth2|1234'; 'dev|crew' in dev
    email         text,
    name          text,
    picture       text,
    role          text NOT NULL DEFAULT 'crew' CHECK (role IN ('admin', 'manager', 'crew')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX users_email_idx ON users (lower(email));

-- Reference sites (the EIA plants already loaded) are public. Sites managers create are private to their members.
-- Defaults to true so scripts/load_sites.py keeps loading public sites; the API sets false for new sites.
ALTER TABLE sites
    ADD COLUMN is_reference boolean NOT NULL DEFAULT true,
    ADD COLUMN description  text,
    ADD COLUMN created_by   uuid REFERENCES users(id) ON DELETE SET NULL;

-- New sites get ids far above any EIA plant code (those are under 100,000).
CREATE SEQUENCE sites_user_id_seq START 9000000 OWNED BY sites.id;
ALTER TABLE sites ALTER COLUMN id SET DEFAULT nextval('sites_user_id_seq');

CREATE TABLE site_members (
    site_id   integer NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    user_id   uuid    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role      text    NOT NULL CHECK (role IN ('manager', 'crew')),
    added_by  uuid REFERENCES users(id) ON DELETE SET NULL,
    added_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (site_id, user_id)
);
CREATE INDEX site_members_user_idx ON site_members (user_id);

-- Who reported, where their phone was (the 5-mile rule checks it), and who resolved it.
ALTER TABLE hazard_reports
    ADD COLUMN reporter_id    uuid REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN gps_latitude   double precision,
    ADD COLUMN gps_longitude  double precision,
    ADD COLUMN gps_accuracy_m real,
    ADD COLUMN resolved_by    uuid REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN resolved_at    timestamptz;
