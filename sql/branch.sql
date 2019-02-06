ALTER TABLE notifications ADD COLUMN idem_key text;

INSERT INTO app_conf (key, value) VALUES
    ('cron_intervals', jsonb_build_object(
        'check_db', (SELECT value::text::int FROM app_conf WHERE key = 'check_db_every'),
        'clean_up_counters', (SELECT value::text::int FROM app_conf WHERE key = 'clean_up_counters_every'),
        'dequeue_emails', (SELECT value::text::int FROM app_conf WHERE key = 'dequeue_emails_every'),
        'fetch_email_bounces', (SELECT value::text::int FROM app_conf WHERE key = 'fetch_email_bounces_every'),
        'notify_patrons', 120,
        'refetch_elsewhere_data', (SELECT value::text::int FROM app_conf WHERE key = 'refetch_elsewhere_data_every'),
        'refetch_repos', (SELECT value::text::int FROM app_conf WHERE key = 'refetch_repos_every'),
        'send_newsletters', (SELECT value::text::int FROM app_conf WHERE key = 'send_newsletters_every')
    ))
    ON CONFLICT (key) DO UPDATE SET value = excluded.value;

SELECT 'after deployment';

DELETE FROM app_conf WHERE key IN (
    'check_db_every', 'clean_up_counters_every', 'dequeue_emails_every',
    'fetch_email_bounces_every', 'refetch_elsewhere_data_every',
    'refetch_repos_every', 'send_newsletters_every'
);
