BEGIN;
    ALTER TABLE elsewhere ADD COLUMN access_token text DEFAULT NULL;
    ALTER TABLE elsewhere ADD COLUMN refresh_token text DEFAULT NULL;
    ALTER TABLE elsewhere ADD COLUMN expires timestamp with time zone DEFAULT NULL;
END;
