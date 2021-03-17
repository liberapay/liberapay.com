BEGIN;
    ALTER TABLE payin_transfers DROP CONSTRAINT IF EXISTS payin_transfers_reversed_amount_check;
    ALTER TABLE payin_transfers ADD CONSTRAINT payin_transfers_reversed_amount_check CHECK (NOT (reversed_amount < 0));
END;
