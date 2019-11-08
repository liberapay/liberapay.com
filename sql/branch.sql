UPDATE email_blacklist
   SET ignore_after = ts + interval '5 days'
 WHERE ignore_after IS NULL
   AND ses_data->'bounce'->>'bounceType' = 'Transient';
