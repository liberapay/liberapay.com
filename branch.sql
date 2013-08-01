BEGIN;
    CREATE TYPE participant_number AS ENUM ('singular', 'plural');

    ALTER TABLE participants ADD COLUMN number participant_number
        NOT NULL DEFAULT 'singular';
    ALTER TABLE log_participant_type ADD COLUMN number participant_number
        NOT NULL DEFAULT 'singular';

    UPDATE participants SET number='plural' WHERE type='group';
    UPDATE log_participant_type SET number='plural' WHERE type='group';

    DROP RULE log_participant_type ON participants;

    ALTER TABLE participants DROP COLUMN type;
    ALTER TABLE log_participant_type DROP COLUMN type;

    ALTER TABLE log_participant_type RENAME TO log_participant_number;

    CREATE RULE log_participant_number
    AS ON UPDATE TO participants
              WHERE NEW.number <> OLD.number
                 DO
        INSERT INTO log_participant_number
                    (ctime, participant, number)
             VALUES ( COALESCE (( SELECT ctime
                                    FROM log_participant_number
                                   WHERE participant=OLD.username
                                   LIMIT 1
                                 ), CURRENT_TIMESTAMP)
                    , OLD.username
                    , NEW.number
                     );
END;
