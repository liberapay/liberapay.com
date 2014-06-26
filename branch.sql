BEGIN;
    ALTER TABLE paydays ADD COLUMN stage integer DEFAULT 0;
    ALTER TABLE participants DROP COLUMN pending;
END;
