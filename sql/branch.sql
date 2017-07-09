ALTER TABLE paydays
    ADD COLUMN stage int,
    ALTER COLUMN stage SET DEFAULT 1;

INSERT INTO app_conf VALUES
    ('s3_payday_logs_bucket', '"archives.liberapay.org"'::jsonb);
