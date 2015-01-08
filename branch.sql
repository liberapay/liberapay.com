BEGIN;
	ALTER TABLE participants ADD COLUMN is_searchable bool NOT NULL DEFAULT TRUE;
END;
