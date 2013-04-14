-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/449


BEGIN;

    -------------------
    -- participant type

    CREATE TYPE participant_type AS ENUM ( 'individual'
                                         , 'group'
                                         , 'open group'
                                          );

    CREATE TABLE log_participant_type
    ( id                serial                      PRIMARY KEY
    , ctime             timestamp with time zone    NOT NULL
    , mtime             timestamp with time zone    NOT NULL
                                                     DEFAULT CURRENT_TIMESTAMP
    , participant       text            NOT NULL REFERENCES participants
                                         ON UPDATE CASCADE ON DELETE RESTRICT
    , type              participant_type    NOT NULL
     );

    ALTER TABLE participants ADD COLUMN type participant_type
        NOT NULL DEFAULT 'individual';

    CREATE RULE log_participant_type
    AS ON UPDATE TO participants
              WHERE NEW.type <> OLD.type
                 DO
        INSERT INTO log_participant_type
                    (ctime, participant, type)
             VALUES ( COALESCE (( SELECT ctime
                                    FROM log_participant_type
                                   WHERE participant=OLD.username
                                   LIMIT 1
                                 ), CURRENT_TIMESTAMP)
                    , OLD.username
                    , NEW.type
                     );


    ------------------
    -- identifications

    CREATE TABLE identifications
    ( id                bigserial   PRIMARY KEY
    , ctime             timestamp with time zone    NOT NULL
    , mtime             timestamp with time zone    NOT NULL
                                                     DEFAULT CURRENT_TIMESTAMP
    , member            text        NOT NULL REFERENCES participants
                                     ON DELETE RESTRICT ON UPDATE CASCADE
    , "group"           text        NOT NULL REFERENCES participants
                                     ON DELETE RESTRICT ON UPDATE CASCADE
    , weight            int         NOT NULL DEFAULT 0
    , identified_by     text        NOT NULL REFERENCES participants
                                     ON DELETE RESTRICT ON UPDATE CASCADE
    , CONSTRAINT no_member_of_self CHECK (member != "group")
    , CONSTRAINT no_self_nomination CHECK (member != "identified_by")
    , CONSTRAINT no_stacking_the_deck CHECK ("group" != "identified_by")
     );


    CREATE VIEW current_identifications AS
    SELECT DISTINCT ON (member, "group", identified_by) *
               FROM identifications
               JOIN participants p ON p.username = identified_by
              WHERE p.is_suspicious IS FALSE
           ORDER BY member
                  , "group"
                  , identified_by
                  , mtime DESC;

END;
