-- Before deployment
BEGIN;

    CREATE TYPE payment_net AS ENUM (
        'balanced-ba', 'balanced-cc', 'paypal', 'bitcoin'
    );

    CREATE TABLE exchange_routes
    ( id            serial         PRIMARY KEY
    , participant   bigint         NOT NULL REFERENCES participants(id)
    , network       payment_net    NOT NULL
    , address       text           NOT NULL CHECK (address <> '')
    , error         text           NOT NULL
    , fee_cap       numeric(35,2)
    , UNIQUE (participant, network, address)
    );

    INSERT INTO exchange_routes
                (participant, network, address, error, fee_cap)
         SELECT id, 'paypal', paypal_email, '', paypal_fee_cap
           FROM participants
          WHERE paypal_email IS NOT NULL;

    INSERT INTO exchange_routes
                (participant, network, address, error)
         SELECT id, 'bitcoin', bitcoin_address, ''
           FROM participants
          WHERE bitcoin_address IS NOT NULL;

    ALTER TABLE exchanges ADD COLUMN route bigint REFERENCES exchange_routes;

    CREATE VIEW current_exchange_routes AS
        SELECT DISTINCT ON (participant, network) *
          FROM exchange_routes
      ORDER BY participant, network, id DESC;

    CREATE CAST (current_exchange_routes AS exchange_routes) WITH INOUT;

END;

-- After deployment
BEGIN;

    ALTER TABLE participants
        DROP COLUMN last_ach_result,
        DROP COLUMN last_bill_result,
        DROP COLUMN paypal_email,
        DROP COLUMN paypal_fee_cap,
        DROP COLUMN bitcoin_address;

END;
