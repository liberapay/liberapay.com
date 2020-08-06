BEGIN;
DROP FUNCTION decrement_rate_limit(text, int, float);
CREATE FUNCTION decrement_rate_limit(a_key text, cap int, period float) RETURNS int AS $$
    WITH updated AS (
             UPDATE rate_limiting AS r
                SET counter = greatest(r.counter - 1 - compute_leak(cap, period, r.ts), 0)
                  , ts = current_timestamp
              WHERE r.key = a_key
          RETURNING counter
         ),
         deleted AS (
             DELETE FROM rate_limiting AS r
              WHERE r.key = a_key
                AND r.counter = 0
         )
    SELECT counter FROM updated;
$$ LANGUAGE sql;
END;
DELETE FROM rate_limiting WHERE counter = 0;
