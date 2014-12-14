BEGIN;

    ALTER TABLE participants ADD COLUMN is_locked bool NOT NULL DEFAULT FALSE;
    ALTER TABLE participants ADD CONSTRAINT claimed_not_locked CHECK (NOT (claimed_time IS NOT NULL AND is_locked));

    UPDATE participants p
       SET is_locked = true
      FROM elsewhere e
     WHERE e.participant = p.username
       AND e.is_locked;

END;
