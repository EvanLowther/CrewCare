-- Notifications for a site's members (crew and managers): new crew reports, danger alerts and the 6 PM briefing.
-- Triggers write them, so they appear the same whether the API (crew reports) or the worker (alerts, briefings)
-- wrote the row. The API streams new ones to open pages and pushes them to phones (Web Push). Admins only hear about
-- sites they're on; everything else they see on the Alerts page.
-- (010 is left for Person A's simulated_weather migration.)

CREATE TABLE notifications (
    id          bigserial   PRIMARY KEY,
    user_id     uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        text        NOT NULL CHECK (kind IN ('crew_report', 'alert', 'briefing')),
    site_id     integer     REFERENCES sites(id) ON DELETE CASCADE,
    severity    text        NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'danger')),
    title       text        NOT NULL,
    body        text,
    link        text,                                -- page to open, e.g. '/sites/621'
    -- What it's about, so one thing notifies each person once: 'report:<id>', 'alert:<id>',
    -- 'briefing:<site>:<date>'. A crew_report alert with meta.report_id shares its report's key (no double ping).
    source_key  text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    read_at     timestamptz,
    pushed_at   timestamptz,                         -- sent to the person's devices (or skipped)
    UNIQUE (user_id, source_key)
);
CREATE INDEX notifications_user_idx ON notifications (user_id, id DESC);
CREATE INDEX notifications_unpushed_idx ON notifications (id) WHERE pushed_at IS NULL;

-- One row per browser or phone that turned on push notifications.
CREATE TABLE push_subscriptions (
    id          bigserial   PRIMARY KEY,
    user_id     uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint    text        NOT NULL UNIQUE,         -- the push service URL for that device
    p256dh      text        NOT NULL,
    auth        text        NOT NULL,
    user_agent  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    last_ok_at  timestamptz
);
CREATE INDEX push_subscriptions_user_idx ON push_subscriptions (user_id);

-- Every member of `site` except `skip_user`.
CREATE FUNCTION notify_site_members(site integer, skip_user uuid, n_kind text, n_severity text, n_title text,
                                    n_body text, n_link text, n_key text) RETURNS void AS $$
    INSERT INTO notifications (user_id, kind, site_id, severity, title, body, link, source_key)
    SELECT m.user_id, n_kind, site, n_severity, n_title, n_body, n_link, n_key
    FROM site_members m
    WHERE m.site_id = site AND m.user_id IS DISTINCT FROM skip_user
    ON CONFLICT (user_id, source_key) DO NOTHING;
$$ LANGUAGE sql;

-- A crew report filed on a site: tell its other members.
CREATE FUNCTION notify_crew_report() RETURNS trigger AS $$
DECLARE
    site_name text;
BEGIN
    IF NEW.site_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT name INTO site_name FROM sites WHERE id = NEW.site_id;
    PERFORM notify_site_members(
        NEW.site_id, NEW.reporter_id, 'crew_report',
        CASE NEW.severity WHEN 'high' THEN 'danger' WHEN 'medium' THEN 'warning' ELSE 'info' END,
        initcap(replace(NEW.hazard_type, '_', ' ')) || ' reported at ' || site_name,
        concat_ws(' · ', NEW.description, 'by ' || NEW.reporter_name),
        '/sites/' || NEW.site_id, 'report:' || NEW.id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER hazard_reports_notify AFTER INSERT ON hazard_reports
    FOR EACH ROW EXECUTE FUNCTION notify_crew_report();

-- A crew_report alert, or any alert that is (or becomes) danger, while active.
CREATE FUNCTION notify_alert() RETURNS trigger AS $$
DECLARE
    site_name text;
BEGIN
    IF NEW.status <> 'active' OR NOT (NEW.type = 'crew_report' OR NEW.severity = 'danger') THEN
        RETURN NEW;
    END IF;
    SELECT name INTO site_name FROM sites WHERE id = NEW.site_id;
    PERFORM notify_site_members(
        NEW.site_id, NULL,
        CASE WHEN NEW.type = 'crew_report' THEN 'crew_report' ELSE 'alert' END,
        NEW.severity, NEW.title || ' · ' || site_name, NEW.message, '/sites/' || NEW.site_id,
        CASE WHEN NEW.type = 'crew_report' AND NEW.meta ? 'report_id' THEN 'report:' || (NEW.meta->>'report_id')
             ELSE 'alert:' || NEW.id END);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER alerts_notify_insert AFTER INSERT ON alerts
    FOR EACH ROW EXECUTE FUNCTION notify_alert();
-- Updates only when it turns danger or active again, not on every refresh of an alert's text.
CREATE TRIGGER alerts_notify_update AFTER UPDATE ON alerts
    FOR EACH ROW WHEN (OLD.severity IS DISTINCT FROM NEW.severity OR OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION notify_alert();

-- A briefing written for a site: tell its members (once per site and day, even if it's regenerated).
CREATE FUNCTION notify_briefing() RETURNS trigger AS $$
DECLARE
    site_name text;
BEGIN
    SELECT name INTO site_name FROM sites WHERE id = NEW.site_id;
    PERFORM notify_site_members(
        NEW.site_id, NULL, 'briefing', 'info',
        'Briefing for ' || site_name || ', ' || to_char(NEW.for_date, 'Dy Mon FMDD'),
        left(NEW.summary, 300), '/briefings?site=' || NEW.site_id,
        'briefing:' || NEW.site_id || ':' || NEW.for_date);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER briefings_notify AFTER INSERT OR UPDATE OF summary ON briefings
    FOR EACH ROW EXECUTE FUNCTION notify_briefing();
