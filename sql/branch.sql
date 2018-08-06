ALTER TYPE payment_net ADD VALUE IF NOT EXISTS 'stripe-card';

INSERT INTO app_conf VALUES
    ('stripe_publishable_key', '"pk_test_rGZY3Q7ba61df50X0h70iHeZ"'::jsonb);

UPDATE app_conf
   SET value = '{"*": true, "mango-ba": false, "mango-bw": false, "mango-cc": false, "stripe-card": true}'::jsonb
 WHERE key = 'payin_methods';

ALTER TABLE payment_accounts ADD COLUMN pk bigserial PRIMARY KEY;

CREATE TYPE payin_status AS ENUM (
    'pre', 'submitting', 'pending', 'succeeded', 'failed'
);

CREATE TABLE payins
( id               bigserial         PRIMARY KEY
, ctime            timestamptz       NOT NULL DEFAULT current_timestamp
, remote_id        text
, payer            bigint            NOT NULL REFERENCES participants
, amount           currency_amount   NOT NULL CHECK (amount > 0)
, status           payin_status      NOT NULL
, error            text
, route            int               NOT NULL REFERENCES exchange_routes
, amount_settled   currency_amount
, fee              currency_amount   CHECK (fee >= 0)
, CONSTRAINT fee_currency_chk CHECK (fee::currency = amount_settled::currency)
, CONSTRAINT success_chk CHECK (NOT (status = 'succeeded' AND (amount_settled IS NULL OR fee IS NULL)))
);

CREATE INDEX payins_payer_idx ON payins (payer);

CREATE TABLE payin_events
( payin          int               NOT NULL REFERENCES payins
, status         payin_status      NOT NULL
, error          text
, timestamp      timestamptz       NOT NULL
, UNIQUE (payin, status)
);

CREATE TYPE payin_transfer_context AS ENUM ('personal-donation', 'team-donation');

CREATE TYPE payin_transfer_status AS ENUM ('pre', 'pending', 'failed', 'succeeded');

CREATE TABLE payin_transfers
( id            serial                   PRIMARY KEY
, ctime         timestamptz              NOT NULL DEFAULT CURRENT_TIMESTAMP
, remote_id     text
, payin         bigint                   NOT NULL REFERENCES payins
, payer         bigint                   NOT NULL REFERENCES participants
, recipient     bigint                   NOT NULL REFERENCES participants
, destination   bigint                   NOT NULL REFERENCES payment_accounts
, context       payin_transfer_context   NOT NULL
, status        payin_transfer_status    NOT NULL
, error         text
, amount        currency_amount          NOT NULL CHECK (amount > 0)
, unit_amount   currency_amount
, n_units       int
, period        donation_period
, team          bigint                   REFERENCES participants
, CONSTRAINT self_chk CHECK (payer <> recipient)
, CONSTRAINT team_chk CHECK ((context = 'team-donation') = (team IS NOT NULL))
, CONSTRAINT period_chk CHECK ((unit_amount IS NULL) = (n_units IS NULL))
);

CREATE INDEX payin_transfers_payer_idx ON payin_transfers (payer);
CREATE INDEX payin_transfers_recipient_idx ON payin_transfers (recipient);

ALTER TABLE exchange_routes ADD COLUMN country text;

CREATE TYPE route_status AS ENUM ('pending', 'chargeable', 'consumed', 'failed', 'canceled');

BEGIN;
    ALTER TABLE exchange_routes ADD COLUMN status route_status;
    UPDATE exchange_routes
       SET status = 'canceled'
     WHERE error = 'invalidated';
    UPDATE exchange_routes
       SET status = 'chargeable'
     WHERE error IS NULL;
END;

SELECT 'after deployment';

BEGIN;
    UPDATE exchange_routes
       SET status = 'canceled'
     WHERE error = 'invalidated';
    UPDATE exchange_routes
       SET status = 'chargeable'
     WHERE error IS NULL;
    ALTER TABLE exchange_routes ALTER COLUMN status SET NOT NULL;
    ALTER TABLE exchange_routes DROP COLUMN error;
END;
