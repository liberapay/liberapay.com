ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'account-switch';
ALTER TABLE transfers
    DROP CONSTRAINT self_chk,
    ADD CONSTRAINT self_chk CHECK ((tipper <> tippee) = (context <> 'account-switch'));

BEGIN;

    ALTER TABLE transfers
        ADD COLUMN wallet_from text,
        ADD COLUMN wallet_to text;

    UPDATE transfers t
       SET wallet_from = (SELECT p.mangopay_wallet_id FROM participants p WHERE p.id = t.tipper)
         , wallet_to = (SELECT p.mangopay_wallet_id FROM participants p WHERE p.id = t.tippee)
         ;

    ALTER TABLE transfers
        ALTER COLUMN wallet_from SET NOT NULL,
        ALTER COLUMN wallet_to SET NOT NULL,
        ADD CONSTRAINT wallets_chk CHECK (wallet_from <> wallet_to);

END;
