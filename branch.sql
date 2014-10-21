BEGIN;
    -- TODO: Migrate the existing emails - there are 766 users with emails attached.
    --       This is to be done before we can delete the existing emails and email types.

    CREATE TABLE emails
    ( id                                serial                      PRIMARY KEY
    , address                           text                        NOT NULL
    , confirmed                         boolean                     DEFAULT NULL
    , nonce                             text
    , ctime                             timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
    , mtime                             timestamp with time zone
    , participant                       text                        NOT NULL REFERENCES participants
    , UNIQUE (address, confirmed) -- One verified email address per person.
     );

    -- The participants table currently has an `email` attribute of type email_address_with confirmation
    -- This should be deleted in the future, once the emails are migrated.
    -- The column we're going to replace it with is named `email_address`. This is only for **verified** emails.
    -- All unverified email stuff happens in the emails table and won't touch this attribute.

    ALTER TABLE participants ADD COLUMN email_address text;

    -- TODO: Add a trigger function to update the email attribute on the user model?.
END;
