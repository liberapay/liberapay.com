BEGIN;
    ALTER TYPE email_address_with_confirmation ADD ATTRIBUTE nonce text;
    ALTER TYPE email_address_with_confirmation ADD ATTRIBUTE ctime timestamp with time zone;
END;
