BEGIN;
    ALTER TABLE elsewhere ADD COLUMN last_fetch_attempt timestamptz;
    ALTER TABLE repositories ADD COLUMN last_fetch_attempt timestamptz;
    DELETE FROM rate_limiting WHERE key LIKE 'refetch_%';
END;
