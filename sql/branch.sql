BEGIN;
    ALTER TABLE participants DROP CONSTRAINT participants_email_key;
    CREATE UNIQUE INDEX participants_email_key ON participants (lower(email));
    ALTER TABLE emails DROP CONSTRAINT emails_address_verified_key;
    CREATE UNIQUE INDEX emails_address_verified_key ON emails (lower(address), verified);
END;
