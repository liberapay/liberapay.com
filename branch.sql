BEGIN;

    ALTER TABLE paydays ADD COLUMN stage integer DEFAULT 0;
    ALTER TABLE participants DROP COLUMN pending;

    CREATE TYPE exchange_status AS ENUM ('pre', 'pending', 'failed', 'succeeded');
    ALTER TABLE exchanges ADD COLUMN status exchange_status;

END;
