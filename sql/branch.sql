SELECT 'after deployment';
BEGIN;
    CREATE TEMPORARY TABLE _tippees ON COMMIT DROP AS (
        SELECT e.participant AS id
             , (CASE WHEN e.payload->>'patron_visibilities' = '2' THEN 2 ELSE 3 END) AS only_accepted_visibility
             , e.ts AS start_time
             , coalesce((
                   SELECT e2.ts
                     FROM events e2
                    WHERE e2.participant = e.participant
                      AND e2.type = 'recipient_settings'
                      AND e2.ts > e.ts
                 ORDER BY e2.ts
                    LIMIT 1
               ), current_timestamp) AS end_time
          FROM events e
         WHERE e.type = 'recipient_settings'
           AND e.payload->>'patron_visibilities' IN ('2', '4')
    );
    UPDATE tips AS tip
       SET visibility = tippee.only_accepted_visibility
      FROM _tippees AS tippee
     WHERE tip.tippee = tippee.id
       AND tip.mtime > tippee.start_time
       AND tip.mtime < tippee.end_time
       AND tip.visibility <> tippee.only_accepted_visibility;
    UPDATE payin_transfers AS pt
       SET visibility = tippee.only_accepted_visibility
      FROM _tippees AS tippee
     WHERE pt.recipient = tippee.id
       AND pt.ctime > tippee.start_time
       AND pt.ctime < tippee.end_time
       AND pt.visibility <> tippee.only_accepted_visibility;
ROLLBACK;
