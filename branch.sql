BEGIN;
    UPDATE elsewhere
       SET avatar_url = concat('https://graph.facebook.com/', user_id, '/picture?width=256&height=256')
     WHERE platform = 'facebook';
END;
