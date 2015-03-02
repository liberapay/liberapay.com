CREATE OR REPLACE FUNCTION enumerate(anyarray)
RETURNS TABLE (rank bigint, value anyelement)
AS $$
    SELECT row_number() over() as rank, value FROM unnest($1) value;
$$ LANGUAGE sql STABLE;
