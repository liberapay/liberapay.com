BEGIN;

DROP INDEX transfers_tipper_tippee_timestamp_idx;
CREATE INDEX transfers_timestamp_idx ON transfers (timestamp);
CREATE INDEX transfers_tipper_idx ON transfers (tipper);
CREATE INDEX transfers_tippee_idx ON transfers (tippee);

END;
