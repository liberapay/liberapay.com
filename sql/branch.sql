BEGIN;
ALTER TABLE payins
    ADD COLUMN allowed_by bigint REFERENCES participants,
    ADD COLUMN allowed_since timestamptz,
    ADD CHECK ((allowed_since IS NULL) = (allowed_by IS NULL));
DROP INDEX events_admin_idx;
CREATE INDEX events_admin_idx ON events (ts DESC) WHERE type IN ('admin_request', 'flags_changed', 'payin_review');
END;
