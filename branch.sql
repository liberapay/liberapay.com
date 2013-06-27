BEGIN;

    -- Whack identifications.
    DROP TABLE identifications CASCADE;


    -- Create a memberships table. Take is an int between 0 and 1000 inclusive,
    -- and is the tenths of a percent that the given member is taking from the
    -- given team. So if my take is 102 for gittip, that means I'm taking 10.2%
    -- of Gittip's budget. The application layer is responsible for ensuring
    -- that current takes sum to 1000 or less for a given team. Any shortfall
    -- is the take for the team itself.

    CREATE TABLE memberships
    ( id                serial                      PRIMARY KEY
    , ctime             timestamp with time zone    NOT NULL
    , mtime             timestamp with time zone    NOT NULL
                                                    DEFAULT CURRENT_TIMESTAMP
    , member            text                        NOT NULL
                                                    REFERENCES participants
                                                    ON UPDATE CASCADE
                                                    ON DELETE RESTRICT
    , team              text                        NOT NULL
                                                    REFERENCES participants
                                                    ON UPDATE CASCADE
                                                    ON DELETE RESTRICT
    , take              numeric(35,2)               NOT NULL DEFAULT 0.0
                                                    CONSTRAINT not_negative
                                                    CHECK (take >= 0)
    , CONSTRAINT no_team_recursion CHECK (team != member)
     );


    -- Create a current_memberships view.
    CREATE OR REPLACE VIEW current_memberships AS
    SELECT DISTINCT ON (member, team) m.*
               FROM memberships m
               JOIN participants p1 ON p1.username = member
               JOIN participants p2 ON p2.username = team
              WHERE p1.is_suspicious IS NOT TRUE
                AND p2.is_suspicious IS NOT TRUE
                AND take > 0
           ORDER BY member
                  , team
                  , mtime DESC;

END;
