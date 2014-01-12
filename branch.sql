BEGIN;
    ALTER TABLE elsewhere ADD COLUMN access_token text DEFAULT NULL;
    ALTER TABLE elsewhere ADD COLUMN refresh_token text DEFAULT NULL;
    ALTER TABLE elsewhere ADD COLUMN expires timestamp with time zone DEFAULT NULL;
END;


-- https://github.com/gittip/www.gittip.com/issues/1164

BEGIN;
    CREATE TABLE bitcoin_addresses
    ( id                serial                      PRIMARY KEY
    , ctime             timestamp with time zone    NOT NULL
    , mtime             timestamp with time zone    NOT NULL
                                                     DEFAULT CURRENT_TIMESTAMP
    , participant       text            NOT NULL REFERENCES participants
                                         ON UPDATE CASCADE ON DELETE RESTRICT
    , bitcoin_address   text            NOT NULL
     );

    ALTER TABLE participants ADD COLUMN bitcoin_address text DEFAULT NULL;

    CREATE RULE bitcoin_addresses
    AS ON UPDATE TO participants
              WHERE NEW.bitcoin_address <> OLD.bitcoin_address
                 DO
        INSERT INTO bitcoin_addresses
                    (ctime, participant, bitcoin_address)
             VALUES ( COALESCE (( SELECT ctime
                                    FROM bitcoin_addresses
                                   WHERE participant=OLD.username
                                   LIMIT 1
                                 ), CURRENT_TIMESTAMP)
                    , OLD.username
                    , NEW.bitcoin_address
                     );

END;
=======


