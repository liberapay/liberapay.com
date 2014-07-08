BEGIN;

    ALTER TABLE participants ADD COLUMN npatrons integer NOT NULL DEFAULT 0;

    CREATE OR REPLACE TEMPORARY VIEW tippees AS
        SELECT tippee, count(*) AS ntippers
          FROM current_tips
          JOIN participants p ON p.username = tipper
         WHERE p.is_suspicious IS NOT TRUE
           AND p.last_bill_result = ''
           AND amount > 0
      GROUP BY tippee;

    UPDATE participants
       SET npatrons = ntippers
      FROM tippees
     WHERE tippee = username;

END;
