BEGIN;

    CREATE TEMPORARY TABLE temp AS
        SELECT archived_as, absorbed_by, balance AS archived_balance
          FROM absorptions a
          JOIN participants p ON a.archived_as = p.username
         WHERE balance > 0;

    INSERT INTO transfers (tipper, tippee, amount)
        SELECT archived_as, absorbed_by, archived_balance
          FROM temp;

    UPDATE participants
       SET balance = (balance - archived_balance)
      FROM temp
     WHERE username = archived_as;

    UPDATE participants
       SET balance = (balance + archived_balance)
      FROM temp
     WHERE username = absorbed_by;

END;
