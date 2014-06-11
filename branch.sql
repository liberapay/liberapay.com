BEGIN;

    ALTER TABLE participants ADD COLUMN giving numeric(35,2) NOT NULL DEFAULT 0;
    ALTER TABLE participants ADD COLUMN pledging numeric(35,2) NOT NULL DEFAULT 0;
    ALTER TABLE participants ADD COLUMN receiving numeric(35,2) NOT NULL DEFAULT 0;

    DROP VIEW backed_tips;  -- This view isn't used at all
    DROP VIEW current_tips;
    CREATE VIEW current_tips AS
        SELECT DISTINCT ON (tipper, tippee) *
          FROM tips
      ORDER BY tipper, tippee, mtime DESC;

    CREATE TEMPORARY TABLE cur_tips AS
        SELECT * FROM current_tips WHERE amount > 0;

    CREATE TEMPORARY VIEW cur_giving AS
        SELECT tipper, sum(amount) AS amount
          FROM cur_tips
          JOIN participants p ON p.username = tippee
         WHERE p.claimed_time IS NOT NULL
           AND p.is_suspicious IS NOT TRUE
      GROUP BY tipper;

    CREATE TEMPORARY VIEW cur_pledging AS
        SELECT tipper, sum(amount) AS amount
          FROM cur_tips
          JOIN participants p ON p.username = tippee
          JOIN elsewhere ON elsewhere.participant = tippee
         WHERE p.claimed_time IS NULL
           AND elsewhere.is_locked = false
           AND p.is_suspicious IS NOT TRUE
      GROUP BY tipper;

    CREATE TEMPORARY VIEW cur_receiving AS
        SELECT tippee, sum(amount) AS amount
          FROM cur_tips
          JOIN participants p ON p.username = tipper
         WHERE p.is_suspicious IS NOT TRUE
           AND p.last_bill_result = ''
      GROUP BY tippee;

    UPDATE participants
       SET giving = amount
      FROM cur_giving
     WHERE tipper = username;

    UPDATE participants
       SET pledging = amount
      FROM cur_pledging
     WHERE tipper = username;

    UPDATE participants
       SET receiving = amount
      FROM cur_receiving
     WHERE tippee = username;

END;
