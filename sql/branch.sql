BEGIN;

    WITH zeroed_tips AS (
             SELECT t.id
               FROM events e
               JOIN current_tips t ON t.tippee = e.participant
                                  AND t.mtime = e.ts
                                  AND t.amount = 0
              WHERE e.type = 'set_status' AND e.payload = '"closed"'
                 OR e.type = 'set_goal' AND e.payload::text LIKE '"-%"'
         )
    DELETE FROM tips t WHERE EXISTS (SELECT 1 FROM zeroed_tips z WHERE z.id = t.id);

END;

SELECT 'after deployment';

UPDATE events
   SET recorder = (payload->>'invitee')::int
 WHERE type IN ('invite_accept', 'invite_refuse');
