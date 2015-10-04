CREATE OR REPLACE FUNCTION enumerate(anyarray)
RETURNS TABLE (rank bigint, value anyelement)
AS $$
    SELECT row_number() over() as rank, value FROM unnest($1) value;
$$ LANGUAGE sql STABLE;


CREATE OR REPLACE FUNCTION min(a anyelement, b anyelement) RETURNS anyelement
AS $$
    SELECT CASE WHEN (a < b) THEN a ELSE b END;
$$ LANGUAGE sql STABLE;


CREATE OR REPLACE FUNCTION round_up(a numeric, b int) RETURNS numeric
AS $$
    SELECT CASE WHEN (trunc(a, b) = a) THEN trunc(a, b) ELSE trunc(a, b) + power(10.0, -b) END;
$$ LANGUAGE sql STABLE;
