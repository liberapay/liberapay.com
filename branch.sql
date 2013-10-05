-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/1369


-- The following lets us cast queries to elsewhere_with_participant to get the
-- participant data dereferenced and returned in a composite type along with
-- the elsewhere data. Then we can register orm.Models in the application for
-- both participant and elsewhere_with_participant, and when we cast queries
-- elsewhere.*::elsewhere_with_participant, we'll get a hydrated Participant
-- object at .participant. Woo-hoo!


BEGIN;

    CREATE TYPE elsewhere_with_participant AS
    -- If Postgres had type inheritance this would be even awesomer.
    ( id            integer
    , platform      text
    , user_id       text
    , user_info     hstore
    , is_locked     boolean
    , participant   participants
     );

    CREATE OR REPLACE FUNCTION load_participant_for_elsewhere (elsewhere)
    RETURNS elsewhere_with_participant
    AS $$

        SELECT $1.id
             , $1.platform
             , $1.user_id
             , $1.user_info
             , $1.is_locked
             , participants.*::participants
          FROM participants
         WHERE participants.username = $1.participant
              ;

    $$ LANGUAGE SQL;


    CREATE CAST (elsewhere AS elsewhere_with_participant)
        WITH FUNCTION load_participant_for_elsewhere(elsewhere);

END;
