CREATE INDEX scheduled_payins_payin_idx ON scheduled_payins (payin);

SELECT 'after deployment';

UPDATE scheduled_payins AS sp
   SET payin = coalesce((
           SELECT pi2.id
             FROM payins pi2
            WHERE pi2.payer = pi.payer
              AND pi2.id > pi.id
              AND pi2.ctime < (pi.ctime + interval '5 minutes')
              AND pi2.amount = pi.amount
              AND pi2.off_session = pi.off_session
              AND pi2.status IN ('pending', 'succeeded')
              AND NOT EXISTS (
                      SELECT 1
                        FROM scheduled_payins sp2
                       WHERE sp2.payin = pi2.id
                  )
         ORDER BY pi2.id
            LIMIT 1
       ), payin)
  FROM payins pi
 WHERE pi.id = sp.payin
   AND pi.status = 'failed'
   AND pi.error LIKE 'For ''sepa_debit'' payments, we currently require %';
