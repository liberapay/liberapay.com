ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'account-switch';
ALTER TABLE transfers
    DROP CONSTRAINT self_chk,
    ADD CONSTRAINT self_chk CHECK ((tipper <> tippee) = (context <> 'account-switch'));

CREATE TABLE mangopay_users
( id            text     PRIMARY KEY
, participant   bigint   NOT NULL REFERENCES participants
);

CREATE OR REPLACE FUNCTION upsert_mangopay_user_id() RETURNS trigger AS $$
    BEGIN
        INSERT INTO mangopay_users
                    (id, participant)
             VALUES (NEW.mangopay_user_id, NEW.id)
        ON CONFLICT (id) DO NOTHING;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER upsert_mangopay_user_id
    AFTER INSERT OR UPDATE OF mangopay_user_id ON participants
    FOR EACH ROW WHEN (NEW.mangopay_user_id IS NOT NULL)
    EXECUTE PROCEDURE upsert_mangopay_user_id();

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

    ALTER TABLE exchange_routes ADD COLUMN remote_user_id text;
    UPDATE exchange_routes r SET remote_user_id = (SELECT p.mangopay_user_id FROM participants p WHERE p.id = r.participant);
    ALTER TABLE exchange_routes ALTER COLUMN remote_user_id SET NOT NULL;

    DROP VIEW current_exchange_routes CASCADE;
    CREATE VIEW current_exchange_routes AS
        SELECT DISTINCT ON (participant, network) *
          FROM exchange_routes
      ORDER BY participant, network, id DESC;
    CREATE CAST (current_exchange_routes AS exchange_routes) WITH INOUT;

    ALTER TABLE cash_bundles ADD COLUMN wallet_id text;
    UPDATE cash_bundles b
       SET wallet_id = (SELECT p.mangopay_wallet_id FROM participants p WHERE p.id = b.owner)
     WHERE owner IS NOT NULL;
    ALTER TABLE cash_bundles
        ALTER COLUMN wallet_id DROP DEFAULT,
        ADD CONSTRAINT wallet_chk CHECK ((wallet_id IS NULL) = (owner IS NULL));

    ALTER TABLE exchanges ADD COLUMN wallet_id text;
    UPDATE exchanges e
       SET wallet_id = (SELECT p.mangopay_wallet_id FROM participants p WHERE p.id = e.participant);
    ALTER TABLE exchanges
        ALTER COLUMN wallet_id DROP DEFAULT,
        ALTER COLUMN wallet_id SET NOT NULL;

END;
