-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/1369

BEGIN;


-- Add new columns

    -- Note: using "user_name" instead of "username" avoids having the same
    --       column name in the participants and elsewhere tables.
    ALTER TABLE elsewhere ADD COLUMN user_name text;
    ALTER TABLE elsewhere ADD COLUMN display_name text;
    ALTER TABLE elsewhere ADD COLUMN email text;
    ALTER TABLE elsewhere ADD COLUMN avatar_url text;
    ALTER TABLE participants ADD COLUMN avatar_url text;
    ALTER TABLE elsewhere ADD COLUMN is_team boolean NOT NULL DEFAULT FALSE;



-- Extract info

    -- Extract user_name from user_info
    UPDATE elsewhere SET user_name = user_id WHERE platform = 'bitbucket';
    UPDATE elsewhere SET user_name = user_info->'display_name' WHERE platform = 'bountysource';
    UPDATE elsewhere SET user_name = user_info->'login' WHERE platform = 'github';
    UPDATE elsewhere SET user_name = user_info->'username' WHERE platform = 'openstreetmap';
    UPDATE elsewhere SET user_name = user_info->'screen_name' WHERE platform = 'twitter';
    UPDATE elsewhere SET user_name = user_info->'username' WHERE platform = 'venmo';

    -- Extract display_name from user_info
    UPDATE elsewhere SET display_name = user_info->'display_name' WHERE platform = 'bitbucket';
    UPDATE elsewhere SET display_name = user_info->'name' WHERE platform = 'github';
    UPDATE elsewhere SET display_name = user_info->'username' WHERE platform = 'openstreetmap';
    UPDATE elsewhere SET display_name = user_info->'name' WHERE platform = 'twitter';
    UPDATE elsewhere SET display_name = user_info->'display_name' WHERE platform = 'venmo';
    UPDATE elsewhere SET display_name = NULL WHERE display_name = 'None';

    -- Extract available email addresses
    UPDATE elsewhere SET email = user_info->'email' WHERE user_info->'email' LIKE '%@%';

    -- Extract available avatar URLs
    UPDATE elsewhere SET avatar_url = concat('https://www.gravatar.com/avatar/',
                                             user_info->'gravatar_id')
                   WHERE platform = 'github'
                     AND user_info->'gravatar_id' != ''
                     AND user_info->'gravatar_id' != 'None';
    UPDATE elsewhere SET avatar_url = concat('https://www.gravatar.com/avatar/',
                                             md5(lower(trim(email))))
                   WHERE email IS NOT NULL AND avatar_url IS NULL;
    UPDATE elsewhere SET avatar_url = user_info->'avatar' WHERE platform = 'bitbucket';
    UPDATE elsewhere SET avatar_url = user_info->'avatar_url'
                   WHERE platform = 'bitbucket' AND avatar_url IS NULL;
    UPDATE elsewhere SET avatar_url = substring(user_info->'links', $$u'avatar': {u'href': u'([^']+)$$)
                   WHERE platform = 'bitbucket' AND avatar_url IS NULL;
    UPDATE elsewhere SET avatar_url = user_info->'image_url' WHERE platform = 'bountysource';
    UPDATE elsewhere SET avatar_url = user_info->'avatar_url' WHERE platform = 'github' AND avatar_url IS NULL;
    UPDATE elsewhere SET avatar_url = user_info->'img_src' WHERE platform = 'openstreetmap';
    UPDATE elsewhere SET avatar_url = replace(user_info->'profile_image_url_https', '_normal.', '.')
                   WHERE platform = 'twitter';
    UPDATE elsewhere SET avatar_url = user_info->'profile_picture_url' WHERE platform = 'venmo';
    UPDATE elsewhere SET avatar_url = NULL WHERE avatar_url = 'None';
    -- Propagate avatar_url to participants
    UPDATE participants p
       SET avatar_url = (
               SELECT avatar_url
                 FROM elsewhere
                WHERE participant = p.username
             ORDER BY platform = 'github' DESC,
                      avatar_url LIKE '%gravatar.com%' DESC
                LIMIT 1
           );

    -- Extract is_team from user_info
    UPDATE elsewhere SET is_team = true WHERE platform = 'bitbucket' AND user_info->'is_team' = 'True';
    UPDATE elsewhere SET is_team = true WHERE platform = 'github' AND lower(user_info->'type') = 'organization';



-- Drop old columns and add new ones

    -- Update user_name constraints
    ALTER TABLE elsewhere ALTER COLUMN user_name SET NOT NULL,
                          ALTER COLUMN user_name DROP DEFAULT;

    -- Replace user_info by a new column of type json (instead of hstore)
    ALTER TABLE elsewhere DROP COLUMN user_info,
                          ADD COLUMN extra_info json;
    DROP EXTENSION hstore;

    -- Simplify homepage_top_* tables
    ALTER TABLE homepage_top_givers DROP COLUMN gravatar_id,
                                    DROP COLUMN twitter_pic,
                                    ADD COLUMN avatar_url text;
    ALTER TABLE homepage_top_receivers DROP COLUMN claimed_time,
                                       DROP COLUMN gravatar_id,
                                       DROP COLUMN twitter_pic,
                                       ADD COLUMN avatar_url text;

    -- The following lets us cast queries to elsewhere_with_participant to get the
    -- participant data dereferenced and returned in a composite type along with
    -- the elsewhere data. Then we can register orm.Models in the application for
    -- both participant and elsewhere_with_participant, and when we cast queries
    -- elsewhere.*::elsewhere_with_participant, we'll get a hydrated Participant
    -- object at .participant. Woo-hoo!

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
             , participants.*::participants
          FROM participants
         WHERE participants.username = $1.participant
              ;
    $$ LANGUAGE SQL;

    CREATE CAST (elsewhere AS elsewhere_with_participant)
        WITH FUNCTION load_participant_for_elsewhere(elsewhere);

END;
