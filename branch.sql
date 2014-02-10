BEGIN;
    DROP TABLE IF EXISTS events;
    CREATE TABLE events
    ( id        serial      PRIMARY KEY
    , ts        timestamp   NOT NULL DEFAULT CURRENT_TIMESTAMP
    , type      text        NOT NULL
    , payload   json
    );

    CREATE INDEX events_ts ON events(ts ASC);
    CREATE INDEX events_type ON events(type);

    /* run branch.py before this
    DROP RULE log_api_key_changes ON participants;
    DROP RULE log_goal_changes ON participants;
    DROP TABLE goals, api_keys;
    DROP SEQUENCE api_keys_id_seq, goals_id_seq;
    */

END;

