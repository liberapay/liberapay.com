BEGIN;
    UPDATE emails
       SET address = trim(substring(address, '^.+@') || lower(substring(address, '[^@]+$')))
     WHERE address <> lower(trim(address))
       AND verified IS TRUE;
    UPDATE participants
       SET email = trim(substring(email, '^.+@') || lower(substring(email, '[^@]+$')))
     WHERE email <> lower(trim(email));
END;
