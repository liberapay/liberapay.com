BEGIN;
ALTER TABLE payin_events ADD COLUMN remote_timestamp timestamptz;
ALTER TABLE payin_transfer_events ADD COLUMN remote_timestamp timestamptz;
END;
