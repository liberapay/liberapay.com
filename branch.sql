BEGIN;
	ALTER TABLE participants ADD COLUMN notify_on_opt_in boolean NOT NULL DEFAULT true;
END;
