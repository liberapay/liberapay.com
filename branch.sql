BEGIN;

    CREATE TYPE context_type AS ENUM
        ('tip', 'take', 'final-gift', 'take-over', 'one-off');

    ALTER TABLE transfers ADD COLUMN context context_type;

    UPDATE transfers t
       SET context = (CASE WHEN as_team_member THEN 'take' ELSE 'tip' END)::context_type
      FROM paydays p
     WHERE t.timestamp > p.ts_start
       AND t.timestamp < p.ts_end;

    UPDATE transfers
       SET context = 'final-gift'
     WHERE context IS NULL
       AND tipper LIKE 'deactivated-%';

    UPDATE transfers
       SET context = 'final-gift'
      FROM participants p
     WHERE context IS NULL
       AND p.username = tipper
       AND p.is_closed IS true;

    -- Treat anomalous transfer as a one-off tip
    UPDATE transfers
       SET context = 'one-off'
     WHERE id = 217522;

    CREATE TEMPORARY TABLE temp AS
        SELECT archived_as, absorbed_by, balance AS archived_balance
          FROM absorptions a
          JOIN participants p ON a.archived_as = p.username
         WHERE balance > 0;

    INSERT INTO transfers (tipper, tippee, amount, context)
        SELECT archived_as, absorbed_by, archived_balance, 'take-over'
          FROM temp;

    UPDATE participants
       SET balance = (balance - archived_balance)
      FROM temp
     WHERE username = archived_as;

    UPDATE participants
       SET balance = (balance + archived_balance)
      FROM temp
     WHERE username = absorbed_by;

    ALTER TABLE transfers DROP COLUMN as_team_member;

    ALTER TABLE transfers ALTER COLUMN context SET NOT NULL;

END;
