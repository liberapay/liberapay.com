BEGIN;

    UPDATE elsewhere
       SET avatar_url = regexp_replace(avatar_url,
              '^https://secure\.gravatar\.com/',
              'https://seccdn.libravatar.org/'
           )
     WHERE avatar_url LIKE '%//secure.gravatar.com/%';

    UPDATE participants
       SET avatar_url = regexp_replace(avatar_url,
              '^https://secure\.gravatar\.com/',
              'https://seccdn.libravatar.org/'
           )
     WHERE avatar_url LIKE '%//secure.gravatar.com/%';

    CREATE TYPE avatar_sources AS ENUM
        ('libravatar', 'bitbucket', 'facebook', 'github', 'google', 'twitter');

    ALTER TABLE participants ADD COLUMN avatar_src avatar_sources;

END;
