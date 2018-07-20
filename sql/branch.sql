INSERT INTO app_conf VALUES
    ('stripe_connect_id', '"ca_DEYxiYHBHZtGj32l9uczcsunbQOcRq8H"'::jsonb),
    ('stripe_secret_key', '"sk_test_QTUa8AqWXyU2feC32glNgDQd"'::jsonb);

ALTER TABLE participants ADD COLUMN has_payment_account boolean;

CREATE TABLE payment_accounts
( participant           bigint          NOT NULL REFERENCES participants
, provider              text            NOT NULL
, id                    text            NOT NULL CHECK (id <> '')
, is_current            boolean         DEFAULT TRUE CHECK (is_current IS NOT FALSE)
, token                 json
, connection_ts         timestamptz     NOT NULL DEFAULT current_timestamp
, UNIQUE (participant, provider, is_current)
, UNIQUE (provider, id, participant)
);

CREATE OR REPLACE FUNCTION update_has_payment_account() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := COALESCE(NEW, OLD);
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

CREATE TRIGGER update_has_payment_account
    AFTER INSERT OR UPDATE OR DELETE ON payment_accounts
    FOR EACH ROW EXECUTE PROCEDURE update_has_payment_account();
