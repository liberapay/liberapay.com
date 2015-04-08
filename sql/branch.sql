BEGIN;
    ALTER TABLE participants ADD COLUMN notify_charge int DEFAULT 1;
    ALTER TABLE participants
        ALTER COLUMN notify_on_opt_in DROP DEFAULT,
        ALTER COLUMN notify_on_opt_in TYPE int USING notify_on_opt_in::int,
        ALTER COLUMN notify_on_opt_in SET DEFAULT 1;
END;
