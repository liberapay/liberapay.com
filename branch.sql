-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/449


BEGIN;

    -------------------
    -- participant kind

    CREATE TYPE participant_type AS ENUM ( 'individual'
                                         , 'group'
                                         , 'open company'
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
    , weight            numeric     DEFAULT 0.1
    , identified_by     text        NOT NULL REFERENCES participants
                                     ON DELETE RESTRICT ON UPDATE CASCADE
    , CONSTRAINT no_member_of_self CHECK (member != "group")
    , CONSTRAINT no_self_nomination CHECK (member != "identified_by")
    , CONSTRAINT no_stacking_the_deck CHECK ("group" != "identified_by")
     );

END;
