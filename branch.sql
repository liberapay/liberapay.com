BEGIN;

    CREATE OR REPLACE TEMPORARY VIEW total_receiving AS
        SELECT tippee, sum(amount) AS amount
          FROM current_tips
          JOIN participants p ON p.username = tipper
         WHERE p.is_suspicious IS NOT TRUE
           AND p.last_bill_result = ''
      GROUP BY tippee;

    UPDATE participants
       SET receiving = amount
      FROM total_receiving
     WHERE tippee = username
       AND receiving <> amount;

END;
