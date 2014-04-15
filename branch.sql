-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/2282

BEGIN;


    -- takes table
    ALTER TABLE memberships RENAME TO takes;
    ALTER TABLE takes RENAME COLUMN take TO amount;

    ALTER TABLE takes DROP CONSTRAINT "memberships_pkey";
    ALTER TABLE takes ADD CONSTRAINT "takes_pkey"
        PRIMARY KEY (id);

    ALTER TABLE takes DROP constraint "memberships_member_fkey";
    ALTER TABLE takes ADD constraint "takes_member_fkey"
        FOREIGN KEY (member) REFERENCES participants(username)
        ON UPDATE CASCADE ON DELETE RESTRICT;

    ALTER TABLE takes DROP constraint "memberships_team_fkey";
    ALTER TABLE takes ADD constraint "takes_team_fkey"
        FOREIGN KEY (team) REFERENCES participants(username)
        ON UPDATE CASCADE ON DELETE RESTRICT;

    ALTER TABLE takes DROP constraint "memberships_recorder_fkey";
    ALTER TABLE takes ADD constraint "takes_recorder_fkey"
        FOREIGN KEY (recorder) REFERENCES participants(username)
        ON UPDATE CASCADE ON DELETE RESTRICT;

    ALTER SEQUENCE memberships_id_seq RENAME TO takes_id_seq;


    -- current_takes view
    DROP VIEW current_memberships;
    CREATE VIEW current_takes AS
    SELECT * FROM (

        SELECT DISTINCT ON (member, team) m.*
                   FROM takes m
                   JOIN participants p1 ON p1.username = member
                   JOIN participants p2 ON p2.username = team
                  WHERE p1.is_suspicious IS NOT TRUE
                    AND p2.is_suspicious IS NOT TRUE
               ORDER BY member
                      , team
                      , mtime DESC

    ) AS anon WHERE amount > 0;

END;
