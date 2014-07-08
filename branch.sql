BEGIN;
    ALTER TABLE participants ADD COLUMN npatrons integer NOT NULL DEFAULT 0;
END;
