CREATE INDEX events_admin_idx ON events (ts DESC) WHERE type = 'admin_request';
