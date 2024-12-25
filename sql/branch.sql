BEGIN;
    ALTER TYPE account_mark ADD VALUE IF NOT EXISTS 'obsolete';
    ALTER TYPE account_mark ADD VALUE IF NOT EXISTS 'out-of-scope';
    ALTER TYPE account_mark ADD VALUE IF NOT EXISTS 'unverifiable';
END;
