BEGIN;
    ALTER TABLE paydays ADD COLUMN week_payins currency_basket;
    UPDATE paydays AS payday
       SET week_payins = (
               SELECT basket_sum(pi.amount)
                 FROM payins pi
                WHERE pi.ctime >= (
                          SELECT previous_payday.ts_start
                            FROM paydays previous_payday
                           WHERE previous_payday.id = payday.id - 1
                      )
                  AND pi.ctime < payday.ts_start
                  AND pi.status = 'succeeded'
           )
     WHERE id >= 132;
END;
