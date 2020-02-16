BEGIN;
    ALTER TABLE notifications ADD COLUMN hide boolean;
    ALTER TABLE notifications
        DROP CONSTRAINT destination_chk,
        ADD CONSTRAINT destination_chk CHECK (email OR web OR hide);
END;
