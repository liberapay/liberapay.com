ALTER TABLE email_blacklist ADD COLUMN ignored_by bigint REFERENCES participants;

UPDATE email_blacklist AS bl
   SET ignore_after = current_timestamp
     , ignored_by = e.participant
  FROM emails e
 WHERE lower(e.address) = lower(bl.address)
   AND e.verified
   AND (bl.ignore_after IS NULL OR bl.ignore_after > current_timestamp)
   AND (bl.reason = 'bounce' AND bl.ts < (e.added_time + interval '24 hours') OR
        bl.reason = 'complaint' AND bl.details = 'disavowed');
