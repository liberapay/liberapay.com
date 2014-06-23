BEGIN;
    ALTER TABLE paydays ADD COLUMN stage integer DEFAULT 0;
END;
