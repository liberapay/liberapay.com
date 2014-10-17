BEGIN;
    ALTER TABLE elsewhere DROP COLUMN access_token,
                          DROP COLUMN refresh_token,
                          DROP COLUMN expires;
    ALTER TABLE elsewhere ADD COLUMN token json;

    DROP TYPE elsewhere_with_participant CASCADE;
    CREATE TYPE elsewhere_with_participant AS
    ( id            integer
    , platform      text
    , user_id       text
    , user_name     text
    , display_name  text
    , email         text
    , avatar_url    text
    , extra_info    json
    , is_locked     boolean
    , is_team       boolean
    , token         json
    , participant   participants
     ); -- If Postgres had type inheritance this would be even awesomer.

    CREATE OR REPLACE FUNCTION load_participant_for_elsewhere (elsewhere)
    RETURNS elsewhere_with_participant
    AS $$
        SELECT $1.id
             , $1.platform
             , $1.user_id
             , $1.user_name
             , $1.display_name
             , $1.email
             , $1.avatar_url
             , $1.extra_info
             , $1.is_locked
             , $1.is_team
             , $1.token
             , participants.*::participants
          FROM participants
         WHERE participants.username = $1.participant
              ;
    $$ LANGUAGE SQL;

    CREATE CAST (elsewhere AS elsewhere_with_participant)
        WITH FUNCTION load_participant_for_elsewhere(elsewhere);

END;
