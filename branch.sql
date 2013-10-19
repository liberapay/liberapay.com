CREATE INDEX participants_claimed_time ON participants (claimed_time DESC) 
  WHERE is_suspicious IS NOT TRUE 
    AND claimed_time IS NOT null;

DROP TABLE homepage_new_participants;
