BEGIN;

    ALTER TABLE participants ADD COLUMN is_closed bool NOT NULL DEFAULT FALSE;

END;
