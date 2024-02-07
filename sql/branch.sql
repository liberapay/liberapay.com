UPDATE participants
   SET avatar_url = 'https://pbs.twimg.com/' || regexp_replace(substr(avatar_url, 24), '%2F', '/', 'g')
 WHERE avatar_url LIKE 'https://nitter.net/pic/%';
