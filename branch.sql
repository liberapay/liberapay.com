BEGIN;

    -- Drop tables we're not using anymore.
    DROP TABLE api_keys;
    DROP TABLE goals;
    DROP TABLE toots;


    -- Drop functions created during new payday.
    DROP FUNCTION process_take();
    DROP FUNCTION process_tip();
    DROP FUNCTION transfer(text, text, numeric, context_type);


    -- Dedent function definition one level.
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
         , participants.*::participants
      FROM participants
     WHERE participants.username = $1.participant
          ;
$$ LANGUAGE SQL;


    -- Switch from `takes m` to `takes t`.
    DROP VIEW current_takes;
    CREATE VIEW current_takes AS
        SELECT * FROM (
             SELECT DISTINCT ON (member, team) t.*
               FROM takes t
               JOIN participants p1 ON p1.username = member
               JOIN participants p2 ON p2.username = team
              WHERE p1.is_suspicious IS NOT TRUE
                AND p2.is_suspicious IS NOT TRUE
           ORDER BY member
                  , team
                  , mtime DESC
        ) AS anon WHERE amount > 0;


    -- Rename participants_api_key to participants_api_key_key.
    ALTER TABLE participants DROP CONSTRAINT participants_api_key;
    ALTER TABLE participants ADD CONSTRAINT participants_api_key_key UNIQUE (api_key);
END;
