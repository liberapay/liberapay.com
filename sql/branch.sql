BEGIN;

CREATE INDEX public_name_trgm_idx ON participants
    USING GIN (lower(public_name) gin_trgm_ops)
    WHERE status = 'active'
      AND public_name IS NOT null;

END;