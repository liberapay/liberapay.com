BEGIN;

UPDATE elsewhere
   SET extra_info = (
           extra_info::jsonb - 'events_url' - 'followers_url' - 'following_url'
           - 'gists_url' - 'html_url' - 'organizations_url' - 'received_events_url'
           - 'repos_url' - 'starred_url' - 'subscriptions_url'
       )::json
 WHERE platform = 'github'
   AND json_typeof(extra_info) = 'object';

UPDATE elsewhere
   SET extra_info = (extra_info::jsonb - 'entities' - 'status')::json
 WHERE platform = 'twitter'
   AND json_typeof(extra_info) = 'object';

END;
