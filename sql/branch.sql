INSERT INTO app_conf VALUES
    ('paypal_domain', '"sandbox.paypal.com"'::jsonb),
    ('paypal_id', '"ASTH9rn8IosjJcEwNYqV2KeHadB6O8MKVP7fL7kXeSuOml0ei77FRYU5E1thEF-1cT3Wp3Ibo0jXIbul"'::jsonb),
    ('paypal_secret', '"EAStyBaGBZk9MVBGrI_eb4O4iEVFPZcRoIsbKDwv28wxLzroLDKYwCnjZfr_jDoZyDB5epQVrjZraoFY"'::jsonb);

ALTER TABLE payment_accounts ALTER COLUMN charges_enabled DROP NOT NULL;

ALTER TYPE payment_net ADD VALUE IF NOT EXISTS 'paypal';

CREATE OR REPLACE FUNCTION update_has_payment_account() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET has_payment_account = (
                   SELECT count(*)
                     FROM payment_accounts
                    WHERE participant = rec.participant
                      AND is_current IS TRUE
               ) > 0
         WHERE id = rec.participant;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;

CREATE TABLE payin_transfer_events
( payin_transfer   int               NOT NULL REFERENCES payin_transfers
, status           payin_status      NOT NULL
, error            text
, timestamp        timestamptz       NOT NULL
, UNIQUE (payin_transfer, status)
);

ALTER TABLE payin_transfers ADD COLUMN fee currency_amount;

ALTER TABLE payins DROP CONSTRAINT success_chk;

ALTER TABLE participants ADD COLUMN payment_providers integer NOT NULL DEFAULT 0;
UPDATE participants SET payment_providers = 1 WHERE has_payment_account;

CREATE TYPE payment_providers AS ENUM ('stripe', 'paypal');

CREATE OR REPLACE FUNCTION update_payment_providers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET payment_providers = (
                   SELECT sum(DISTINCT array_position(
                                           enum_range(NULL::payment_providers),
                                           provider::payment_providers
                                       ))
                     FROM payment_accounts
                    WHERE participant = rec.participant
                      AND is_current IS TRUE
               )
         WHERE id = rec.participant;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_payment_providers
    AFTER INSERT OR UPDATE OR DELETE ON payment_accounts
    FOR EACH ROW EXECUTE PROCEDURE update_payment_providers();

SELECT 'after deployment';

UPDATE participants SET payment_providers = 1 WHERE has_payment_account;
DROP TRIGGER update_has_payment_account ON payment_accounts;
DROP FUNCTION update_has_payment_account();
ALTER TABLE participants DROP COLUMN has_payment_account;
