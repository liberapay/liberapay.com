CREATE OR REPLACE FUNCTION compute_arrears(tip tips) RETURNS currency_amount AS $$
    SELECT coalesce_currency_amount((
               SELECT sum(tip_at_the_time.amount, tip.amount::currency)
                 FROM paydays payday
                 JOIN LATERAL (
                          SELECT tip2.*
                            FROM tips tip2
                           WHERE tip2.tipper = tip.tipper
                             AND tip2.tippee = tip.tippee
                             AND tip2.mtime < payday.ts_start
                        ORDER BY tip2.mtime DESC
                           LIMIT 1
                      ) tip_at_the_time ON true
                WHERE payday.ts_start > tip.ctime
                  AND payday.ts_start > '2018-08-15'
                  AND payday.ts_end > payday.ts_start
                  AND tip_at_the_time.renewal_mode > 0
                  AND NOT EXISTS (
                          SELECT 1
                            FROM transfers tr
                           WHERE tr.tipper = tip.tipper
                             AND coalesce(tr.team, tr.tippee) = tip.tippee
                             AND tr.context IN ('tip', 'take')
                             AND tr.timestamp >= payday.ts_start
                             AND tr.timestamp <= payday.ts_end
                             AND tr.status = 'succeeded'
                      )
           ), tip.amount::currency) - coalesce_currency_amount((
               SELECT sum(tr.amount, tip.amount::currency)
                 FROM transfers tr
                WHERE tr.tipper = tip.tipper
                  AND coalesce(tr.team, tr.tippee) = tip.tippee
                  AND tr.context IN ('tip-in-arrears', 'take-in-arrears')
                  AND tr.status = 'succeeded'
           ), tip.amount::currency);
$$ LANGUAGE sql;
