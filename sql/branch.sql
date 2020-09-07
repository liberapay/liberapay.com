SELECT 'after deployment';

UPDATE participants
   SET avatar_url = 'https://nitter.net/pic/' || regexp_replace(substr(avatar_url, 23), '/', '%2F')
 WHERE avatar_url LIKE 'https://pbs.twimg.com/%';
