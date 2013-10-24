CREATE INDEX participants_claimed_time ON participants (claimed_time DESC) 
  WHERE is_suspicious IS NOT TRUE 
    AND claimed_time IS NOT null;

DROP TABLE homepage_new_participants;

ALTER TABLE homepage_top_receivers ADD COLUMN gravatar_id text;
ALTER TABLE homepage_top_receivers ADD COLUMN twitter_pic text;

ALTER TABLE homepage_top_givers ADD COLUMN gravatar_id text;
ALTER TABLE homepage_top_givers ADD COLUMN twitter_pic text;
