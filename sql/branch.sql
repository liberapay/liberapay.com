CREATE UNLOGGED TABLE rate_limiting
( key       text          PRIMARY KEY
, counter   int           NOT NULL
, ts        timestamptz   NOT NULL
);

CREATE OR REPLACE FUNCTION compute_leak(cap int, period float, last_leak timestamptz) RETURNS int AS $$
    SELECT trunc(cap * extract(epoch FROM current_timestamp - last_leak) / period)::int;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION hit_rate_limit(key text, cap int, period float) RETURNS int AS $$
    INSERT INTO rate_limiting AS r
                (key, counter, ts)
         VALUES (key, 1, current_timestamp)
    ON CONFLICT (key) DO UPDATE
            SET counter = r.counter + 1 - least(compute_leak(cap, period, r.ts), r.counter)
              , ts = current_timestamp
          WHERE (r.counter - compute_leak(cap, period, r.ts)) < cap
      RETURNING cap - counter;
$$ LANGUAGE sql;

CREATE OR REPLACE FUNCTION clean_up_counters(pattern text, period float) RETURNS bigint AS $$
    WITH deleted AS (
        DELETE FROM rate_limiting
              WHERE key LIKE pattern
                AND ts < (current_timestamp - make_interval(secs => period))
          RETURNING 1
    ) SELECT count(*) FROM deleted;
$$ LANGUAGE sql;

SELECT hit_rate_limit('test', 1, 0.2) = 0;      -- 1st hit - allowed
SELECT hit_rate_limit('test', 1, 0.2) is null;  -- 2nd hit - blocked
SELECT pg_sleep(0.2);
SELECT hit_rate_limit('test', 1, 0.2) = 0;      -- 3rd hit - allowed, the counter has been fully reset due to elapsed time
SELECT hit_rate_limit('test', 2, 0.2) = 0;      -- 4th hit - allowed, the cap has been raised
SELECT hit_rate_limit('test', 2, 0.2) is null;  -- 5th hit - blocked
SELECT hit_rate_limit('test', 2, 0.2) is null;  -- 5th hit - still blocked
SELECT pg_sleep(0.1);
SELECT hit_rate_limit('test', 2, 0.2) = 0;      -- 6th hit - allowed, the counter has been decreased by 1 due to elapsed time
SELECT hit_rate_limit('test', 2, 0.2) is null;  -- 7th hit - blocked
SELECT pg_sleep(0.1);
SELECT clean_up_counters('test', 0.01) = 1;


INSERT INTO app_conf (key, value) VALUES
    ('clean_up_counters_every', '3600'::jsonb),
    ('trusted_proxies', '[]'::jsonb);
