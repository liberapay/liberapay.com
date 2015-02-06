BEGIN;
    ALTER TABLE participants DROP CONSTRAINT participants_api_key_key;
    ALTER TABLE participants ADD COLUMN old_auth_usage date;
END;
