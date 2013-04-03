-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/141

-- Create a goals table to track all goals a participant has stated over time.
CREATE TABLE goals
( id                    serial                      PRIMARY KEY
, ctime                 timestamp with time zone    NOT NULL
, mtime                 timestamp with time zone    NOT NULL
                                                    DEFAULT CURRENT_TIMESTAMP
, participant           text                        NOT NULL
                                                    REFERENCES participants
                                                    ON UPDATE CASCADE
                                                    ON DELETE RESTRICT
, goal                  numeric(35,2)               DEFAULT NULL
 );


BEGIN;

    -- Migrate data from goal column of participants over to new goals table.
    INSERT INTO goals (ctime, mtime, participant, goal)
         SELECT CURRENT_TIMESTAMP
              , CURRENT_TIMESTAMP
              , id
              , goal
           FROM participants
          WHERE goal IS NOT NULL;

    -- Create a rule to log changes to participant.goal into goals.
    CREATE RULE log_goal_changes
    AS ON UPDATE TO participants
              WHERE (OLD.goal IS NULL AND NOT NEW.goal IS NULL)
                 OR (NEW.goal IS NULL AND NOT OLD.goal IS NULL)
                 OR NEW.goal <> OLD.goal
                 DO
        INSERT INTO goals
                    (ctime, participant, goal)
             VALUES ( COALESCE (( SELECT ctime
                                    FROM goals
                                   WHERE participant=OLD.id
                                   LIMIT 1
                                 ), CURRENT_TIMESTAMP)
                    , OLD.id
                    , NEW.goal
                     );

END;
