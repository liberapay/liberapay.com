BEGIN;
    ALTER TABLE notification_queue ADD COLUMN ts timestamptz;
    ALTER TABLE notification_queue ALTER COLUMN ts SET DEFAULT now();
END;
