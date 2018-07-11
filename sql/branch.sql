INSERT INTO app_conf VALUES
    ('stripe_connect_id', '"ca_DEYxiYHBHZtGj32l9uczcsunbQOcRq8H"'::jsonb),
    ('stripe_secret_key', '"sk_test_QTUa8AqWXyU2feC32glNgDQd"'::jsonb);

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
