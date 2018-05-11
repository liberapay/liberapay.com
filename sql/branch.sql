ALTER TABLE elsewhere DROP COLUMN email;
ALTER TABLE elsewhere ADD COLUMN description text;

SELECT 'after deployment';

BEGIN;
    UPDATE elsewhere
       SET description = extra_info->>'bio'
     WHERE platform IN ('facebook', 'github', 'gitlab')
       AND length(extra_info->>'bio') > 0;
    UPDATE elsewhere
       SET description = extra_info->>'aboutMe'
     WHERE platform = 'google'
       AND length(extra_info->>'aboutMe') > 0;
    UPDATE elsewhere
       SET description = extra_info->>'note'
     WHERE platform = 'mastodon'
       AND length(extra_info->>'note') > 0;
    UPDATE elsewhere
       SET description = extra_info->'osm'->'user'->>'description'
     WHERE platform = 'openstreetmap'
       AND length(extra_info->'osm'->'user'->>'description') > 0;
    UPDATE elsewhere
       SET description = extra_info->>'description'
     WHERE platform IN ('twitch', 'twitter')
       AND length(extra_info->>'description') > 0;
    UPDATE elsewhere
       SET description = extra_info->'snippet'->>'description'
     WHERE platform = 'youtube'
       AND length(extra_info->'snippet'->>'description') > 0;
END;
