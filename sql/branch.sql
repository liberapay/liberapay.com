ALTER TABLE elsewhere
    ADD COLUMN info_fetched_at timestamptz NOT NULL DEFAULT '1970-01-01T00:00:00+00'::timestamptz,
    ALTER COLUMN info_fetched_at SET DEFAULT current_timestamp;

INSERT INTO app_conf VALUES
    ('refetch_elsewhere_data_every', '120'::jsonb);

CREATE OR REPLACE FUNCTION check_rate_limit(key text, cap int, period float) RETURNS boolean AS $$
    SELECT coalesce(
        ( SELECT counter - least(compute_leak(cap, period, r.ts), r.counter)
            FROM rate_limiting AS r
           WHERE r.key = key
        ), 0
    ) < cap;
$$ LANGUAGE sql;
