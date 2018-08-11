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
