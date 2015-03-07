BEGIN;
    ALTER TABLE participants ADD COLUMN notifications text[] NOT NULL DEFAULT '{}';
END;
