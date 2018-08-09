INSERT INTO app_conf VALUES
    ('paypal_domain', '"sandbox.paypal.com"'::jsonb),
    ('paypal_id', '"ASTH9rn8IosjJcEwNYqV2KeHadB6O8MKVP7fL7kXeSuOml0ei77FRYU5E1thEF-1cT3Wp3Ibo0jXIbul"'::jsonb),
    ('paypal_secret', '"EAStyBaGBZk9MVBGrI_eb4O4iEVFPZcRoIsbKDwv28wxLzroLDKYwCnjZfr_jDoZyDB5epQVrjZraoFY"'::jsonb);

ALTER TABLE payment_accounts ALTER COLUMN charges_enabled DROP NOT NULL;
