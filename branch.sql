BEGIN;

    INSERT INTO tips (tipper, tippee, amount, ctime)
        SELECT tipper, tippee, 0
             , ( SELECT ctime
                   FROM tips
                  WHERE tipper=tipper
                    AND tippee=tippee
                  LIMIT 1
               )
          FROM current_tips
          JOIN participants p ON p.username = tippee
         WHERE p.goal < 0
           AND amount > 0;

    CREATE OR REPLACE TEMPORARY VIEW total_giving AS
        SELECT tipper, COALESCE(sum(amount), 0) AS amount
          FROM current_tips
          JOIN participants p ON p.username = tippee
         WHERE p.is_suspicious IS NOT TRUE
           AND p.claimed_time IS NOT NULL
      GROUP BY tipper;

    UPDATE participants
       SET giving = amount
      FROM total_giving
     WHERE tipper = username
       AND giving <> amount;

    CREATE OR REPLACE TEMPORARY VIEW total_receiving AS
        SELECT tippee, sum(amount) AS amount
          FROM current_tips
          JOIN participants p ON p.username = tipper
         WHERE p.is_suspicious IS NOT TRUE
           AND p.last_bill_result = ''
      GROUP BY tippee;

    UPDATE participants
       SET receiving = (amount + taking)
      FROM total_receiving
     WHERE tippee = username
       AND receiving <> (amount + taking);

END;
