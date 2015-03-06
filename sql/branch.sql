BEGIN;
    ALTER TABLE participants ADD COLUMN notify_charge int DEFAULT 1;
END;
