BEGIN;

    UPDATE participants
       SET goal = -1
     WHERE is_locked;

    INSERT INTO tips (tipper, tippee, amount, ctime)
        SELECT tipper, tippee, 0, t.ctime
          FROM current_tips t
          JOIN participants p ON p.username = tippee
         WHERE amount > 0
           AND p.is_locked;

    -- Uncomment when deploying
    -- ALTER TABLE participants DROP COLUMN is_locked;

END;
