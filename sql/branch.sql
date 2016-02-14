BEGIN;

    ALTER TABLE paydays ADD COLUMN nusers bigint NOT NULL DEFAULT 0,
                        ADD COLUMN week_deposits numeric(35,2) NOT NULL DEFAULT 0,
                        ADD COLUMN week_withdrawals numeric(35,2) NOT NULL DEFAULT 0;

    WITH week_exchanges AS (
             SELECT e.*, (
                        SELECT p.id
                          FROM paydays p
                         WHERE e.timestamp < p.ts_start
                      ORDER BY p.ts_start DESC
                         LIMIT 1
                    ) AS payday_id
               FROM exchanges e
              WHERE status <> 'failed'
         )
    UPDATE paydays p
       SET nusers = (
               SELECT count(*)
                 FROM participants
                WHERE kind IN ('individual', 'organization')
                  AND join_time < p.ts_start
                  AND status = 'active'
           )
         , week_deposits = (
               SELECT COALESCE(sum(amount), 0)
                 FROM week_exchanges
                WHERE payday_id = p.id
                  AND amount > 0
           )
         , week_withdrawals = (
               SELECT COALESCE(-sum(amount), 0)
                 FROM week_exchanges
                WHERE payday_id = p.id
                  AND amount < 0
           );

END;
