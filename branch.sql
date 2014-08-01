BEGIN;

    ALTER TABLE paydays ADD COLUMN stage integer DEFAULT 0;
    ALTER TABLE participants DROP COLUMN pending;

    CREATE TYPE exchange_status AS ENUM ('pre', 'pending', 'failed', 'succeeded');
    ALTER TABLE exchanges ADD COLUMN status exchange_status;

    UPDATE participants
       SET last_ach_result = NULL
     WHERE last_ach_result = 'NoResultFound()';
    UPDATE participants
       SET last_bill_result = NULL
     WHERE last_bill_result = 'NoResultFound()';

    INSERT INTO tips (ctime, tipper, tippee, amount)
        SELECT ctime, tipper, tippee, 0 FROM tips WHERE id = 46266;

END;
