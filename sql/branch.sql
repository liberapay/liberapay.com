INSERT INTO app_conf VALUES
    ('check_email_domains', 'true'::jsonb);

INSERT INTO app_conf VALUES
    ('paypal_domain', '"sandbox.paypal.com"'::jsonb),
    ('paypal_id', '"ASTH9rn8IosjJcEwNYqV2KeHadB6O8MKVP7fL7kXeSuOml0ei77FRYU5E1thEF-1cT3Wp3Ibo0jXIbul"'::jsonb),
    ('paypal_secret', '"EAStyBaGBZk9MVBGrI_eb4O4iEVFPZcRoIsbKDwv28wxLzroLDKYwCnjZfr_jDoZyDB5epQVrjZraoFY"'::jsonb);

ALTER TABLE payment_accounts ALTER COLUMN charges_enabled DROP NOT NULL;

ALTER TYPE payment_net ADD VALUE IF NOT EXISTS 'paypal';

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
           SET payment_providers = coalesce((
                   SELECT sum(DISTINCT array_position(
                                           enum_range(NULL::payment_providers),
                                           a.provider::payment_providers
                                       ))
                     FROM payment_accounts a
                    WHERE ( a.participant = rec.participant OR
                            a.participant IN (
                                SELECT t.member
                                  FROM current_takes t
                                 WHERE t.team = rec.participant
                            )
                          )
                      AND a.is_current IS TRUE
                      AND a.verified IS TRUE
               ), 0)
         WHERE id = rec.participant
            OR id IN (
                   SELECT t.team FROM current_takes t WHERE t.member = rec.participant
               );
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_payment_providers
    AFTER INSERT OR UPDATE OR DELETE ON payment_accounts
    FOR EACH ROW EXECUTE PROCEDURE update_payment_providers();

ALTER TABLE payment_accounts ADD COLUMN verified boolean NOT NULL DEFAULT TRUE;

SELECT 'after deployment';

DROP TRIGGER update_has_payment_account ON payment_accounts;
DROP FUNCTION update_has_payment_account();
ALTER TABLE participants DROP COLUMN has_payment_account;

-- The following dummy operation is to trigger update_payment_providers
UPDATE payment_accounts SET id = id;

ALTER TABLE payment_accounts ALTER COLUMN verified DROP DEFAULT;
