BEGIN;

    -- Update user_id and is_team. See branch.py for doco.
    \i update.sql


    -- Drop all Bitbucket accounts that aren't required for account access.

    DELETE FROM elsewhere WHERE id IN (
        SELECT e1.id
          FROM elsewhere e1
          JOIN elsewhere e2
            ON e1.participant = e2.participant
         WHERE e1.platform='bitbucket'
               AND e2.platform IN ('twitter', 'github', 'facebook', 'google', 'openstreetmap')
               AND NOT e2.is_team
    );

END;
