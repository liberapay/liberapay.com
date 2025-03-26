BEGIN;
    DROP INDEX events_admin_idx;
    CREATE INDEX events_admin_idx ON events (ts DESC) WHERE type IN ('admin_request', 'flags_changed');
END;
