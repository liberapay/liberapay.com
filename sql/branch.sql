CREATE TYPE blacklist_reason AS ENUM ('bounce', 'complaint');

CREATE TABLE email_blacklist
( address        text               NOT NULL
, ts             timestamptz        NOT NULL DEFAULT current_timestamp
, reason         blacklist_reason   NOT NULL
, details        text
, ses_data       jsonb
, ignore_after   timestamptz
, report_id      text
);

CREATE INDEX email_blacklist_idx ON email_blacklist (lower(address));
CREATE UNIQUE INDEX email_blacklist_report_idx ON email_blacklist (report_id, address)
    WHERE report_id IS NOT NULL;

INSERT INTO app_conf VALUES
    ('fetch_email_bounces_every', '60'::jsonb),
    ('ses_feedback_queue_url', '""'::jsonb);
