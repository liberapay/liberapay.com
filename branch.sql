BEGIN;
	ALTER TABLE participants ADD COLUMN search_opt_out bool NOT NULL DEFAULT FALSE;
END;
