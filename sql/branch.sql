ALTER TABLE paydays
    ADD COLUMN stage int,
    ALTER COLUMN stage SET DEFAULT 1;

INSERT INTO app_conf VALUES
    ('s3_payday_logs_bucket', '"archives.liberapay.org"'::jsonb);

INSERT INTO app_conf VALUES
    ('bot_github_username', '"liberapay-bot"'::jsonb),
    ('bot_github_token', '""'::jsonb),
    ('payday_repo', '"liberapay-bot/test"'::jsonb),
    ('payday_label', '"Payday"'::jsonb);
