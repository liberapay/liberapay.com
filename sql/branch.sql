ALTER TABLE takes
    DROP CONSTRAINT not_negative,
    ADD CONSTRAINT amount_chk CHECK (amount IS NULL OR amount >= 0 OR (amount).amount = -1),
    ALTER COLUMN amount DROP DEFAULT;
