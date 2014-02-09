BEGIN;
    DROP TABLE IF EXISTS events;
    CREATE TABLE events
    ( id        serial      PRIMARY KEY
    , ctime     timestamp   NOT NULL DEFAULT CURRENT_TIMESTAMP
    , pid1      bigint      NOT NULL
    , pid2      bigint
    , action    text        NOT NULL
    , params    json
    );

    CREATE INDEX events_ctime ON events(ctime ASC);
    CREATE INDEX events_pid1 ON events(pid1);
    CREATE INDEX events_pid2 ON events(pid2);
    CREATE INDEX events_action ON events(action);

    -- claim
    INSERT INTO events (ctime, pid1, pid2, action, params)
        SELECT p.claimed_time AT TIME ZONE 'UTC' as ctime
             , p.id AS pid1
             , NULL AS pid2
             , 'participant.claim' AS action
             , '{}' AS params
        FROM participants p
        WHERE claimed_time IS NOT NULL
        ORDER BY ctime ASC;

    -- username
    INSERT INTO events (ctime, pid1, pid2, action, params)
        SELECT (p.claimed_time + interval '0.01 second') AT TIME ZONE 'UTC' as ctime
             , p.id AS pid1
             , NULL AS pid2
             , 'participant.set' AS action
             , to_json(hstore('username', p.username)) AS params
        FROM participants p
        WHERE claimed_time IS NOT NULL
        ORDER BY ctime ASC;

END;

