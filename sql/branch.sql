CREATE OR REPLACE FUNCTION decrement_rate_limit(key text, cap int, period float) RETURNS int AS $$
    UPDATE rate_limiting AS r
       SET counter = greatest(r.counter - 1 - compute_leak(cap, period, r.ts), 0)
              , ts = current_timestamp
     WHERE r.key = key
 RETURNING counter;
$$ LANGUAGE sql;
