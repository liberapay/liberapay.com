BEGIN;
    CREATE TABLE emails
    ( id            serial                      PRIMARY KEY
    , address       text                        NOT NULL
    , verified      boolean                     DEFAULT NULL
                                                  CONSTRAINT verified_cant_be_false
                                                    -- Only use TRUE and NULL, so that the unique
                                                    -- constraint below functions properly.
                                                    CHECK (verified IS NOT FALSE)
    , nonce         text
    , ctime         timestamp with time zone    NOT NULL
                                                  DEFAULT CURRENT_TIMESTAMP
    , mtime         timestamp with time zone
    , participant   text                        NOT NULL
                                                  REFERENCES participants
                                                  ON UPDATE CASCADE
                                                  ON DELETE RESTRICT

    , UNIQUE (address, verified) -- A verified email address can't be linked to multiple
                                 -- participants. However, an *un*verified address *can*
                                 -- be linked to multiple participants. We implement this
                                 -- by using NULL instead of FALSE for the unverified
                                 -- state, hence the check constraint on verified.
    , UNIQUE (participant, address)
     );

    -- The participants table currently has an `email` attribute of type
    -- email_address_with confirmation. This should be deleted in the future,
    -- once the emails are migrated. The column we're going to replace it with
    -- is named `email_address`. This is only for **verified** emails. All
    -- unverified email stuff happens in the emails table and won't touch this
    -- attribute.

    ALTER TABLE participants ADD COLUMN email_address text UNIQUE,
                             ADD COLUMN email_lang text;

    UPDATE events
       SET payload = replace(replace( payload::text, '"set"', '"add"')
                                    , '"current_email"'
                                    , '"email"'
                                     )::json
     WHERE payload->>'action' = 'set'
       AND (payload->'values'->'current_email') IS NOT NULL;

END;
