ALTER TABLE elsewhere
    ADD COLUMN info_fetched_at timestamptz NOT NULL DEFAULT '1970-01-01T00:00:00+00'::timestamptz,
    ALTER COLUMN info_fetched_at SET DEFAULT current_timestamp;

INSERT INTO app_conf VALUES
    ('refetch_elsewhere_data_every', '120'::jsonb);
